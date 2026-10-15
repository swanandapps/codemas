import hashlib
import hmac
import json
import os
import uuid
from datetime import timedelta
from unittest import mock

import boto3
from botocore.stub import Stubber
from django.core.exceptions import ImproperlyConfigured
from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from exams.models import Exam, Question
from jobs.models import Job
from jobs.relay import tick
from jobs.services import enqueue
from jobs.transports import LocalTransport, SqsTransport, get_transport
from submissions.models import Submission

QUEUE = 'https://sqs.ap-southeast-1.amazonaws.com/123456789012/codemas-exec'
SCRUB_VARS = ('AWS_LAMBDA_FUNCTION_NAME', 'CODEMAS_EXEC_SCRUB')
RELAY_SECRET = 'relay-test-secret'


def expected_token(job, secret=RELAY_SECRET):
    """Computed here independently of jobs.signing: HMAC-SHA256(secret, "job:<id>"), hex."""
    return hmac.new(secret.encode(), f'job:{job.id}'.encode(), hashlib.sha256).hexdigest()


def make(sid):
    with transaction.atomic():
        return enqueue(Job.KIND_EXECUTE, sid)


def stubbed_sqs():
    # a real botocore client with fake credentials; the Stubber answers every call, so nothing leaves the process
    client = boto3.client('sqs', region_name='ap-southeast-1', aws_access_key_id='x', aws_secret_access_key='x')
    return client, Stubber(client)


@override_settings(JOB_QUEUE_URL=QUEUE, JOB_SIGNING_SECRET=RELAY_SECRET)
class SqsTransportTest(TestCase):
    def setUp(self):
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        student = User.objects.create_user(username='s', password='pw', role='student')
        exam = Exam.objects.create(title='E', created_by=trainer)
        q = Question.objects.create(exam=exam, title='Q', description='d')
        self.sub = Submission.objects.create(student=student, exam=exam, question=q, code='x',
                                             language='javascript', attempt_number=1)

    @staticmethod
    def entry(job, language):
        return {'Id': str(job.id),
                'MessageBody': json.dumps({'job_id': str(job.id), 'kind': 'execute_submission',
                                           'token': expected_token(job)}),
                'MessageAttributes': {'job_id': {'DataType': 'String', 'StringValue': str(job.id)},
                                      'language': {'DataType': 'String', 'StringValue': language}}}

    @staticmethod
    def ok(job):
        return {'Id': str(job.id), 'MessageId': str(uuid.uuid4()), 'MD5OfMessageBody': 'x'}

    def expect_batch(self, stub, entries, successful, failed=()):
        stub.add_response('send_message_batch', {'Successful': list(successful), 'Failed': list(failed)},
                          {'QueueUrl': QUEUE, 'Entries': entries})

    def test_publish_sends_the_job_id_and_language_in_a_batch(self):
        client, stub = stubbed_sqs()
        job = make(self.sub.id)
        self.expect_batch(stub, [self.entry(job, 'javascript')], [self.ok(job)])
        with stub:
            self.assertEqual(tick(SqsTransport(client=client)), 1)
            stub.assert_no_pending_responses()
        job.refresh_from_db()
        self.assertEqual(job.status, 'queued')

    def test_each_message_carries_its_own_jobs_token_and_nothing_else(self):
        client, stub = stubbed_sqs()
        a, b = make(self.sub.id), make(900001)
        sent = []
        stub.add_response('send_message_batch', {'Successful': [self.ok(a), self.ok(b)], 'Failed': []})
        client.meta.events.register('before-parameter-build.sqs.SendMessageBatch',
                                    lambda params, **kw: sent.extend(params['Entries']))
        with stub:
            self.assertEqual(tick(SqsTransport(client=client)), 2)
        bodies = {e['Id']: json.loads(e['MessageBody']) for e in sent}
        for job in (a, b):
            self.assertEqual(bodies[str(job.id)], {'job_id': str(job.id), 'kind': 'execute_submission',
                                                  'token': expected_token(job)})
        self.assertNotEqual(bodies[str(a.id)]['token'], bodies[str(b.id)]['token'])
        self.assertNotIn(RELAY_SECRET, json.dumps(sent))

    def test_jobs_go_out_in_chunks_of_ten(self):
        client, stub = stubbed_sqs()
        jobs = [make(self.sub.id)] + [make(900000 + i) for i in range(11)]  # 12 jobs, oldest first
        langs = ['javascript'] + ['unknown'] * 11  # deleted submissions still go out, as 'unknown'
        entries = [self.entry(j, l) for j, l in zip(jobs, langs)]
        self.expect_batch(stub, entries[:10], [self.ok(j) for j in jobs[:10]])
        self.expect_batch(stub, entries[10:], [self.ok(j) for j in jobs[10:]])
        with stub:
            self.assertEqual(tick(SqsTransport(client=client)), 12)
            stub.assert_no_pending_responses()

    def test_a_partial_batch_failure_queues_only_the_accepted_jobs(self):
        client, stub = stubbed_sqs()
        a, b, c = make(self.sub.id), make(900001), make(900002)
        self.expect_batch(stub, [self.entry(a, 'javascript'), self.entry(b, 'unknown'), self.entry(c, 'unknown')],
                          [self.ok(a), self.ok(c)],
                          [{'Id': str(b.id), 'SenderFault': False, 'Code': 'InternalError', 'Message': 'try again'}])
        with stub:
            self.assertEqual(tick(SqsTransport(client=client)), 2)
        for j in (a, b, c):
            j.refresh_from_db()
        self.assertEqual((a.status, b.status, c.status), ('queued', 'pending', 'queued'))
        self.assertIsNone(b.published_at)
        self.assertEqual(b.last_error, 'publish failed: InternalError: try again')

    def test_an_entry_missing_from_the_response_is_not_marked_queued(self):
        client, stub = stubbed_sqs()
        a, b = make(self.sub.id), make(900001)
        self.expect_batch(stub, [self.entry(a, 'javascript'), self.entry(b, 'unknown')], [self.ok(a)])
        with stub:
            self.assertEqual(tick(SqsTransport(client=client)), 1)
        b.refresh_from_db()
        self.assertEqual(b.status, 'pending')

    def test_an_sqs_error_leaves_the_job_pending_and_stops_the_tick(self):
        client, stub = stubbed_sqs()
        jobs = [make(self.sub.id)] + [make(900000 + i) for i in range(11)]
        stub.add_client_error('send_message_batch', service_error_code='AWS.SimpleQueueService.NonExistentQueue',
                              http_status_code=400)
        with stub:  # one failed call, not one per chunk: the queue is down for all of them
            self.assertEqual(tick(SqsTransport(client=client)), 0)
            stub.assert_no_pending_responses()
        for job in jobs:
            job.refresh_from_db()
            self.assertEqual(job.status, 'pending')
            self.assertIsNone(job.published_at)
            self.assertIn('NonExistentQueue', job.last_error)

    @override_settings(AWS_REGION='eu-west-1')
    def test_default_client_uses_the_configured_region(self):
        with mock.patch('boto3.client') as factory:
            t = SqsTransport()
        self.assertIs(t.client, factory.return_value)
        args, kwargs = factory.call_args
        self.assertEqual((args, kwargs['region_name']), (('sqs',), 'eu-west-1'))
        config = kwargs['config']  # a hung queue must not stall the relay for minutes
        self.assertEqual((config.connect_timeout, config.read_timeout), (3, 5))
        self.assertEqual(config.retries, {'mode': 'standard', 'max_attempts': 3})

    @override_settings(JOB_QUEUE_URL='')
    def test_missing_queue_url_is_a_configuration_error(self):
        with self.assertRaises(ImproperlyConfigured):
            SqsTransport(client=mock.Mock())


class GetTransportTest(TestCase):
    @override_settings(JOB_TRANSPORT='sqs', JOB_QUEUE_URL=QUEUE)
    def test_sqs(self):
        with mock.patch('boto3.client'):
            self.assertIsInstance(get_transport(), SqsTransport)

    @override_settings(JOB_TRANSPORT='local')
    def test_local(self):
        with mock.patch.dict(os.environ):
            t = get_transport()
            self.assertIsInstance(t, LocalTransport)
            t.close()

    @override_settings(JOB_TRANSPORT='sq s')
    def test_unknown_transport_is_an_error_not_a_silent_fallback(self):
        with self.assertRaises(ImproperlyConfigured):
            get_transport()


@override_settings(CODEMAS_API_URL='http://relay-test:1', JOB_SIGNING_SECRET=RELAY_SECRET)
class LocalTransportTest(TestCase):
    def setUp(self):
        patcher = mock.patch.dict(os.environ)
        patcher.start()
        self.addCleanup(patcher.stop)
        for var in SCRUB_VARS + ('CODEMAS_API_URL', 'JOB_SIGNING_SECRET'):
            os.environ.pop(var, None)

    def test_never_turns_on_the_sandbox_scrub(self):
        """sandbox.py scrubs the temp dir and kills same-uid processes when either variable is set.
        On a developer's machine that would wipe their temp dir, so the local transport must not set them."""
        t = LocalTransport(workers=1)
        t.close()
        for var in SCRUB_VARS:
            self.assertNotIn(var, os.environ)
        with mock.patch.object(t.handler.sandbox, 'IS_LINUX', True):  # as on a Linux dev box or CI
            self.assertFalse(t.handler.sandbox.scrub_enabled())

    def test_exports_the_api_url_but_never_the_secret_to_the_handler(self):
        LocalTransport(workers=1).close()
        self.assertEqual(os.environ['CODEMAS_API_URL'], 'http://relay-test:1')
        self.assertNotIn('JOB_SIGNING_SECRET', os.environ)  # the handler gets a per-job token instead

    def test_publish_runs_the_handler_with_an_sqs_shaped_event_and_no_context(self):
        t = LocalTransport(workers=1)
        job = make(1)
        with mock.patch.object(t.handler, 'handler', return_value={'batchItemFailures': []}) as h:
            t.publish(job)
            t.close(wait=True)
        h.assert_called_once_with({'Records': [{'messageId': str(job.id),
                                                'body': json.dumps({'job_id': str(job.id), 'kind': job.kind,
                                                                    'token': expected_token(job)})}]},
                                  None)

    def failing_then(self, *results):
        """Handler results in order; an Exception instance is raised."""
        def handler(event, context):
            r = results[min(handler.calls, len(results) - 1)]
            handler.calls += 1
            if isinstance(r, Exception):
                raise r
            return r
        handler.calls = 0
        return handler

    def test_a_reported_failure_is_redelivered_like_sqs(self):
        job = make(1)
        failed = {'batchItemFailures': [{'itemIdentifier': str(job.id)}]}
        sleeps = []
        t = LocalTransport(workers=1, redeliver_delays=(2, 5), wait=lambda s: sleeps.append(s) or False)
        h = self.failing_then(failed, {'batchItemFailures': []})
        with mock.patch.object(t.handler, 'handler', h):
            t.publish(job)
            t.close(wait=True)
        self.assertEqual((h.calls, sleeps), (2, [2]))

    def test_redelivery_is_bounded_at_three_deliveries(self):
        job = make(1)
        sleeps = []
        t = LocalTransport(workers=1, redeliver_delays=(2, 5), wait=lambda s: sleeps.append(s) or False)
        h = self.failing_then(RuntimeError('boom'))  # raises every time
        with mock.patch.object(t.handler, 'handler', h):
            t.publish(job)
            t.close(wait=True)  # the error is logged in the worker thread, never raised here
        self.assertEqual((h.calls, sleeps), (3, [2, 5]))

    def test_default_backoff_is_two_then_five_seconds(self):
        self.assertEqual(LocalTransport.REDELIVER_DELAYS, (2, 5))

    def test_close_without_wait_cancels_the_backlog_and_cuts_backoff_short(self):
        import threading
        started, release = threading.Event(), threading.Event()
        calls = []

        def slow(event, context):
            calls.append(event['Records'][0]['messageId'])
            started.set()
            release.wait(5)
            return {'batchItemFailures': [{'itemIdentifier': 'x'}]}  # would be redelivered after 60 s
        t = LocalTransport(workers=1, redeliver_delays=(60,))
        jobs = [make(i) for i in (1, 2, 3)]
        with mock.patch.object(t.handler, 'handler', slow):
            for j in jobs:
                t.publish(j)
            self.assertTrue(started.wait(5))
            t.close()  # returns at once; the two queued deliveries are cancelled
            release.set()
            import time
            began = time.monotonic()
            t.pool.shutdown(wait=True)  # the in-flight call ends without its 60 s backoff
            self.assertLess(time.monotonic() - began, 5)
        self.assertEqual(calls, [str(jobs[0].id)])  # no redelivery, no cancelled deliveries
