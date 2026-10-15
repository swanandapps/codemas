"""codemas-exec: grades one submission per SQS message.

1. claim the job from Django with the message's per-job token -> code, test inputs, limits, lease token
2. run every test in the sandbox
3. complete the job with each test's output (Django decides pass/fail and records it)

No database credentials, no shared secret, no expected outputs and no third-party packages: everything
goes through Django over HTTPS. The token in each SQS message was minted by the relay and works only
for that one job.
"""
import json
import os
import sys
import time
import urllib.error
import urllib.request

# Lambda puts this directory on sys.path already; this covers loading handler.py by file path
# (the backend's local transport does that).
_HERE = os.path.dirname(os.path.abspath(__file__))
if _HERE not in sys.path:
    sys.path.insert(0, _HERE)

import sandbox  # noqa: E402

PR_SET_DUMPABLE = 4


def _protect_environ():
    """Make this process non-dumpable so student code can't read /proc/<our pid>/environ (which
    holds the role's AWS credentials) or /proc/<our pid>/mem. On Lambda this is not enough on its own:
    the runtime's other processes expose the same credentials (accepted risk R2). Popping variables
    from os.environ would not help: /proc/<pid>/environ shows the environment the process was
    started with. Children reset to dumpable on exec, so this only protects the grader."""
    if not sys.platform.startswith('linux'):
        return
    try:
        import ctypes
        libc = ctypes.CDLL(None, use_errno=True)
        if libc.prctl(PR_SET_DUMPABLE, 0, 0, 0, 0) != 0:
            raise OSError(ctypes.get_errno(), 'prctl(PR_SET_DUMPABLE) failed')
    except Exception as e:  # fail soft, loudly
        print(json.dumps({'warning': 'could not make the grader non-dumpable; '
                                     'student code may be able to read its environment', 'error': repr(e)}))


_protect_environ()


def _selfcheck():
    """One JSON line per cold start saying whether the sandbox really blocks network sockets."""
    try:
        blocked = sandbox.egress_blocked()
    except Exception:
        blocked = None
    print(json.dumps({'event': 'sandbox_selfcheck', 'egress_blocked': blocked}))


_selfcheck()

ACK = ('done', 'gone', 'dead')  # the job needs no more work: acknowledge the message
HTTP_TIMEOUT_S = 15
# Before starting a test, keep enough Lambda time for that test's worst case plus the complete call.
RESERVE_MS = (HTTP_TIMEOUT_S + 5) * 1000
# Don't claim a job (which spends one of its attempts) without time for at least one
# worst-case test at the default 10 s limit; leave the message for a fresh invocation instead.
CLAIM_MIN_MS = 10 * 1000 + RESERVE_MS
# Django refuses request bodies over DATA_UPLOAD_MAX_MEMORY_SIZE (2.5 MB by default) with a 400,
# which would send a student's grade to the DLQ as an infrastructure failure. Stay well under it.
MAX_BODY_BYTES = 2_000_000
TRUNCATED = '\n[output truncated]'
FIRST_CAP_CHARS = 64 * 1024  # the sandbox already caps each stream at output_kb (64 KB)
MIN_CAP_CHARS = 256


def _encode(payload):
    """UTF-8 JSON. With ensure_ascii=False, U+FFFD (invalid UTF-8 from the student) is 3 bytes, not 6."""
    return json.dumps(payload, ensure_ascii=False).encode('utf-8')


def _json(raw):
    try:
        data = json.loads(raw or b'{}')
        return data if isinstance(data, dict) else {}
    except ValueError:  # e.g. a proxy's HTML error page
        return {'error': raw[:200].decode('utf-8', errors='replace')}


def _post(path, payload):
    """POST JSON to Django. The payload carries the job token; there are no signature headers."""
    body = payload if isinstance(payload, bytes) else _encode(payload)
    url = os.environ['CODEMAS_API_URL'].rstrip('/') + path
    req = urllib.request.Request(url, data=body, method='POST',
                                 headers={'Content-Type': 'application/json; charset=utf-8'})
    try:
        with urllib.request.urlopen(req, timeout=HTTP_TIMEOUT_S) as resp:
            return resp.status, _json(resp.read())
    except urllib.error.HTTPError as e:
        return e.code, _json(e.read())


def _remaining_ms(context):
    getter = getattr(context, 'get_remaining_time_in_millis', None)
    return getter() if getter else None


class BudgetExhausted(Exception):
    """The Lambda would time out before the next test could finish: an infrastructure limit."""


NOT_RUN_AFTER_TIMEOUT = {'output': '', 'error': 'Not run: an earlier test exceeded the time limit',
                         'ms': 0, 'timed_out': True}


def _run_tests(job, context):
    """Run the tests in order.
    - After the first student timeout the code is already too slow (the grade is decided), so the
      rest are reported as not run instead of each burning its full time limit.
    - If the Lambda's own time runs out before that, raise BudgetExhausted: that's our limit, not
      the student's, so it must never become a failing grade."""
    limits = job['limits']
    needed_ms = int(limits['timeout_s']) * 1000 + RESERVE_MS
    results, student_timed_out = [], False
    for t in job['tests']:
        if student_timed_out:
            outcome = NOT_RUN_AFTER_TIMEOUT
        else:
            remaining = _remaining_ms(context)
            if remaining is not None and remaining < needed_ms:
                raise BudgetExhausted
            outcome = sandbox.run(job['language'], job['code'], t['input'], limits)
            student_timed_out = outcome['timed_out']
        results.append({'test_id': t['id'], **outcome})
    return results


def _trim(text, cap):
    return text if len(text) <= cap else text[:cap] + TRUNCATED


def _complete_body(job, results):
    """The /complete/ body, encoded, under MAX_BODY_BYTES. Measured on the encoded bytes because
    JSON escapes control characters to 6 bytes each, so a character budget can't bound it. While it
    is too big, halve the per-field cap and trim every output and error to it, all alike: the handler
    never sees expected outputs, so it can't tell a right answer from a wrong one. A right answer is
    lost only when the whole body is over ~2 MB (about 30+ tests near the 64 KB output cap)."""
    payload = {'job_id': job['job_id'], 'token': job['token'], 'lease_token': job['lease_token'],
               'results': results}
    body = _encode(payload)
    cap = FIRST_CAP_CHARS
    while len(body) > MAX_BODY_BYTES and cap > MIN_CAP_CHARS:
        cap = max(cap // 2, MIN_CAP_CHARS)
        trimmed = [{**r, 'output': _trim(r.get('output') or '', cap), 'error': _trim(r.get('error') or '', cap)}
                   for r in results]
        body = _encode({**payload, 'results': trimmed})
    return body


def _release(job_id, token, lease_token, error):
    """Hand the job back with /fail/: Django puts it back in its outbox and the relay republishes it.
    True when Django took it, so the message is acknowledged (SQS retrying as well would only spend
    receives toward the DLQ). False if the release itself failed: then SQS must retry the message."""
    try:
        status, out = _post('/internal/jobs/fail/', {'job_id': job_id, 'token': token, 'lease_token': lease_token,
                                                     'error': error})
    except Exception as e:  # unreachable Django
        print(json.dumps({'job_id': job_id, 'release_error': repr(e)}))
        return False
    if not 200 <= status < 300:
        print(json.dumps({'job_id': job_id, 'release': status, 'error': out.get('error')}))
        return False
    return True


def _grade(job_id, token, context):
    """Returns True when the message can be acknowledged, False to have SQS retry it."""
    started = time.monotonic()
    remaining = _remaining_ms(context)
    if remaining is not None and remaining < CLAIM_MIN_MS:
        print(json.dumps({'job_id': job_id, 'skipped': 'not enough time left to claim', 'remaining_ms': remaining}))
        return False
    status, job = _post('/internal/jobs/claim/', {'job_id': job_id, 'token': token})
    if status != 200:
        print(json.dumps({'job_id': job_id, 'claim': status, 'error': job.get('error')}))
        return job.get('error') in ACK and status in (409, 410)
    try:
        # zero tests -> empty results; Django records that as an 'error' submission, never a pass
        results = _run_tests(job, context)
    except BudgetExhausted:  # release the lease; a fresh invocation retries it
        print(json.dumps({'job_id': job_id, 'grader_error': 'grading time budget exhausted'}))
        return _release(job_id, token, job['lease_token'], 'grading time budget exhausted')
    except Exception as e:  # infrastructure problem in the grader itself: release the lease
        print(json.dumps({'job_id': job_id, 'grader_error': repr(e)}))
        return _release(job_id, token, job['lease_token'], repr(e))
    body = _complete_body({**job, 'job_id': job_id, 'token': token}, results)
    status, done = _post('/internal/jobs/complete/', body)
    print(json.dumps({'job_id': job_id, 'submission_id': job.get('submission_id'), 'language': job['language'],
                      'tests': len(results), 'submission_status': done.get('submission_status'),
                      'complete': status, 'duration_ms': int((time.monotonic() - started) * 1000)}))
    return status in (200, 409)  # 409 stale: a newer lease owns it; nothing for us to retry


def handler(event, context):
    failures = []
    for record in event.get('Records', []):
        try:
            message = json.loads(record['body'])
            ok = _grade(message['job_id'], message['token'], context)
        except Exception as e:  # unreachable Django, bad message: let SQS retry, then DLQ
            print(json.dumps({'messageId': record.get('messageId'), 'error': repr(e)}))
            ok = False
        if not ok:
            failures.append({'itemIdentifier': record['messageId']})
    return {'batchItemFailures': failures}
