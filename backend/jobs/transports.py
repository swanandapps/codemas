"""Where the relay sends a published job.

local  runs the real Lambda handler (lambda/exec/handler.py) in a thread pool. Laptops and tests; no AWS.
sqs    sends the job id to the codemas-exec queue; SQS triggers the Lambda.

Both carry only {"job_id", "kind", "token"}: the handler claims everything else from Django. The token is
jobs.signing.job_token(job_id), minted here by the trusted relay; the executor never holds JOB_SIGNING_SECRET.
"""
import importlib.util
import json
import logging
import os
import threading
from concurrent.futures import ThreadPoolExecutor

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured

from .models import Job
from .signing import job_token

log = logging.getLogger(__name__)


def _message(job):
    return json.dumps({'job_id': str(job.id), 'kind': job.kind, 'token': job_token(job.id)})


_handler_module = None
_handler_lock = threading.Lock()


def _load_handler():
    """Import lambda/exec/handler.py by path, once. It puts its own directory on sys.path for `import sandbox`."""
    global _handler_module
    with _handler_lock:
        if _handler_module is None:
            path = settings.LAMBDA_EXEC_DIR / 'handler.py'
            spec = importlib.util.spec_from_file_location('codemas_exec_handler', path)
            module = importlib.util.module_from_spec(spec)
            spec.loader.exec_module(module)
            _handler_module = module
    return _handler_module


class Transport:
    """publish_many(jobs) -> {str(job.id): None if the transport accepted it, else an error string}.
    The relay marks only the accepted jobs queued. Subclasses implement publish(job) (one at a time,
    raising on failure) or override publish_many for a native batch call."""

    def publish(self, job):
        raise NotImplementedError

    def publish_many(self, jobs):
        outcome = {}
        for job in jobs:
            try:
                self.publish(job)
                outcome[str(job.id)] = None
            except Exception as e:
                outcome[str(job.id)] = repr(e)
        return outcome

    def close(self, wait=False):
        pass


class LocalTransport(Transport):
    """Runs the real Lambda handler code in a thread pool, with context=None (no time-budget guard).

    It emulates SQS redelivery: a record the handler reports in batchItemFailures (or a handler crash)
    is delivered again after REDELIVER_DELAYS, so at most 1 + len(REDELIVER_DELAYS) deliveries. Duplicate
    deliveries are harmless: claim is locked and leased, a second claim gets 409 busy/done, and only the
    lease holder can complete. Whatever is still unfinished after that comes back through /fail/ (pending)
    or the sweep.

    It never sets AWS_LAMBDA_FUNCTION_NAME or CODEMAS_EXEC_SCRUB: either one turns on sandbox.py's
    between-runs scrub, which on a developer's machine would wipe their temp dir and kill their processes."""

    REDELIVER_DELAYS = (2, 5)  # seconds before the 2nd and 3rd delivery

    def __init__(self, workers=4, redeliver_delays=REDELIVER_DELAYS, wait=None):
        # the handler reads this from os.environ on every call. Not JOB_SIGNING_SECRET: like the
        # Lambda, the handler only ever sees the per-job token in each message.
        os.environ.setdefault('CODEMAS_API_URL', settings.CODEMAS_API_URL)
        self.handler = _load_handler()
        self.pool = ThreadPoolExecutor(max_workers=workers, thread_name_prefix='codemas-exec')
        self.redeliver_delays = tuple(redeliver_delays)
        self._stop = threading.Event()
        # wait(seconds) -> True when the transport is closing; injectable so tests don't sleep
        self._wait = wait or self._stop.wait

    def publish(self, job):
        event = {'Records': [{'messageId': str(job.id), 'body': _message(job)}]}
        self.pool.submit(self._deliver, event)

    def _deliver(self, event):
        for delay in self.redeliver_delays + (None,):
            if self._handle_once(event):
                return
            if delay is None:
                log.warning('local executor gave up on %s after %d deliveries; /fail/ or the sweep will retry it',
                            event['Records'][0]['messageId'], len(self.redeliver_delays) + 1)
                return
            if self._wait(delay) or self._stop.is_set():  # closing: leave it to /fail/ or the sweep
                return

    def _handle_once(self, event):
        try:
            result = self.handler.handler(event, None)
        except Exception:  # the handler catches per record; this is a bug in it, treat like a failed delivery
            log.exception('local executor crashed')
            return False
        return not (result or {}).get('batchItemFailures')

    def close(self, wait=False):
        """wait=True (run_relay --once, tests): finish everything published, redeliveries included.
        wait=False (Ctrl-C): cancel deliveries that haven't started, cut backoffs short, return at once.
        A handler call already running finishes on its own (bounded by the sandbox and HTTP timeouts);
        a job abandoned here is still pending/queued/running in the database, so the relay recovers it."""
        if wait:
            self.pool.shutdown(wait=True)
            return
        self._stop.set()
        self.pool.shutdown(wait=False, cancel_futures=True)


SQS_BATCH = 10  # send_message_batch limit


class SqsTransport(Transport):
    """Sends job ids to the codemas-exec queue, ten per call. Lambda is triggered by SQS."""

    def __init__(self, client=None):
        if not settings.JOB_QUEUE_URL:
            raise ImproperlyConfigured('JOB_TRANSPORT=sqs needs JOB_QUEUE_URL')
        if client is None:
            import boto3
            from botocore.config import Config
            # short timeouts: the relay holds its row locks while publishing
            client = boto3.client('sqs', region_name=settings.AWS_REGION, config=Config(
                connect_timeout=3, read_timeout=5, retries={'mode': 'standard', 'max_attempts': 3}))
        self.client = client
        self.url = settings.JOB_QUEUE_URL

    def _languages(self, jobs):
        from submissions.models import Submission
        ids = [j.subject_id for j in jobs if j.kind == Job.KIND_EXECUTE]
        return dict(Submission.objects.filter(pk__in=ids).values_list('id', 'language'))

    def publish_many(self, jobs):
        languages = self._languages(jobs)
        outcome = {}
        for i in range(0, len(jobs), SQS_BATCH):
            chunk = jobs[i:i + SQS_BATCH]
            entries = [{
                'Id': str(job.id), 'MessageBody': _message(job),
                'MessageAttributes': {
                    'job_id': {'DataType': 'String', 'StringValue': str(job.id)},
                    'language': {'DataType': 'String', 'StringValue': languages.get(job.subject_id) or 'unknown'}},
            } for job in chunk]
            try:
                resp = self.client.send_message_batch(QueueUrl=self.url, Entries=entries)
            except Exception as e:
                # the queue is unreachable or refusing: don't spend a timeout per chunk; all stay pending
                for job in jobs[i:]:
                    outcome[str(job.id)] = repr(e)
                break
            for ok in resp.get('Successful', []):
                outcome[ok['Id']] = None
            for bad in resp.get('Failed', []):
                outcome[bad['Id']] = f"{bad.get('Code', 'Failed')}: {bad.get('Message', '')}".strip()
        return outcome

    def publish(self, job):
        error = self.publish_many([job]).get(str(job.id), 'no result')
        if error is not None:
            raise RuntimeError(error)


def get_transport():
    kind = settings.JOB_TRANSPORT
    if kind == 'sqs':
        return SqsTransport()
    if kind == 'local':
        return LocalTransport()
    # no silent fallback: a typo in production must not start running student code on the web host
    raise ImproperlyConfigured(f"JOB_TRANSPORT must be 'local' or 'sqs', not {kind!r}")
