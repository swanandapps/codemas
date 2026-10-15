import ast
import json
import os
import sys
import threading
import time
import unittest
import urllib.error
from http.server import BaseHTTPRequestHandler, HTTPServer
from unittest import mock

sys.path.insert(0, __file__.rsplit('/tests/', 1)[0])
import handler  # noqa: E402

LIMITS = {'timeout_s': 3, 'python_memory_mb': 256, 'node_heap_mb': 192, 'output_kb': 64}
LINUX = sys.platform.startswith('linux')


# The secret variable name, spelled in two parts so a grep of lambda/ for it stays empty.
SECRET_VAR = 'JOB_SIGNING' + '_SECRET'


def token_for(jid):
    """The per-job token the relay would mint. The handler never computes one: it echoes the message's."""
    return f'tok-{jid}'


class FakeDjango(BaseHTTPRequestHandler):
    claims = {}      # job_id -> (status, body)
    completed = []
    failed = []
    rejected = []    # requests refused with 401
    headers_seen = []  # (path, header names) of every request
    complete_reply = (200, {'status': 'succeeded', 'submission_status': 'passed'})
    fail_reply = (200, {'status': 'released'})
    body_sizes = []  # (path, bytes) of every request
    MAX_BODY = 2_621_440  # Django's default DATA_UPLOAD_MAX_MEMORY_SIZE: bigger bodies get 400

    def do_POST(self):
        body = self.rfile.read(int(self.headers['Content-Length']))
        FakeDjango.body_sizes.append((self.path, len(body)))
        FakeDjango.headers_seen.append((self.path, {k.lower() for k in self.headers.keys()}))
        data = json.loads(body.decode('utf-8'))  # Django's json.loads(request.body) decodes UTF-8 too
        # same rule as jobs.signing.token_ok: the body carries this job's token
        ok = data.get('token') == token_for(data.get('job_id'))
        raw = None
        if len(body) > FakeDjango.MAX_BODY:  # RequestDataTooBig
            code, out = 400, {'error': 'request body too big'}
        elif not ok:
            FakeDjango.rejected.append(self.path)
            code, out = 401, {'error': 'bad token'}
        elif self.path == '/internal/jobs/claim/':
            code, out = self.claims[data['job_id']]
            if isinstance(out, bytes):  # a non-JSON body, e.g. a proxy's HTML error page
                raw = out
        elif self.path == '/internal/jobs/complete/':
            FakeDjango.completed.append(data)
            code, out = FakeDjango.complete_reply
        else:
            FakeDjango.failed.append(data)
            code, out = FakeDjango.fail_reply
        payload = raw if raw is not None else json.dumps(out).encode()
        self.send_response(code)
        self.send_header('Content-Type', 'application/json')
        self.send_header('Content-Length', str(len(payload)))
        self.end_headers()
        self.wfile.write(payload)

    def log_message(self, *args):
        pass


def job(jid, code='print(int(input())*2)', tests=None, language='python'):
    """A claim response as Django sends it: tests are [{id, input}], never the expected output."""
    if tests is None:
        tests = [{'id': 1, 'input': '2'}, {'id': 2, 'input': '5'}]
    return (200, {'job_id': jid, 'lease_token': 'tok', 'kind': 'execute_submission', 'submission_id': 5,
                  'language': language, 'code': code, 'tests': tests, 'limits': LIMITS})


class FakeContext:
    def __init__(self, remaining_ms):
        self.remaining_ms = remaining_ms

    def get_remaining_time_in_millis(self):
        return self.remaining_ms


class HandlerTest(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.server = HTTPServer(('127.0.0.1', 0), FakeDjango)
        threading.Thread(target=cls.server.serve_forever, daemon=True).start()
        handler.os.environ['CODEMAS_API_URL'] = f'http://127.0.0.1:{cls.server.server_port}'
        handler.os.environ.pop(SECRET_VAR, None)  # the Lambda no longer has it

    @classmethod
    def tearDownClass(cls):
        cls.server.shutdown()
        cls.server.server_close()

    def setUp(self):
        FakeDjango.completed.clear()
        FakeDjango.failed.clear()
        FakeDjango.rejected.clear()
        FakeDjango.body_sizes.clear()
        FakeDjango.headers_seen.clear()
        FakeDjango.complete_reply = (200, {'status': 'succeeded', 'submission_status': 'passed'})
        FakeDjango.fail_reply = (200, {'status': 'released'})
        quiet = mock.patch('builtins.print')  # the handler logs one JSON line per job
        quiet.start()
        self.addCleanup(quiet.stop)

    def event(self, *job_ids):
        return {'Records': [{'messageId': f'm-{j}', 'body': json.dumps({'job_id': j, 'kind': 'execute_submission',
                                                                         'token': token_for(j)})}
                            for j in job_ids]}

    def test_sends_the_messages_token_on_claim_and_complete_and_no_signature_headers(self):
        FakeDjango.claims['tk'] = job('tk')
        self.assertEqual(handler.handler(self.event('tk'), None), {'batchItemFailures': []})
        self.assertEqual(FakeDjango.rejected, [])
        self.assertEqual(FakeDjango.completed[-1]['token'], token_for('tk'))
        self.assertEqual([p for p, _ in FakeDjango.headers_seen], ['/internal/jobs/claim/', '/internal/jobs/complete/'])
        for path, names in FakeDjango.headers_seen:
            self.assertNotIn('x-signature', names, path)
            self.assertNotIn('x-timestamp', names, path)

    def test_fail_carries_the_token_and_the_lease(self):
        FakeDjango.claims['ft'] = job('ft')
        with mock.patch.object(handler.sandbox, 'run', side_effect=OSError('disk full')):
            self.assertEqual(handler.handler(self.event('ft'), None), {'batchItemFailures': []})
        self.assertEqual({k: FakeDjango.failed[-1][k] for k in ('job_id', 'token', 'lease_token')},
                         {'job_id': 'ft', 'token': token_for('ft'), 'lease_token': 'tok'})

    def test_a_wrong_token_is_refused_and_retried(self):
        FakeDjango.claims['wt'] = job('wt')
        event = {'Records': [{'messageId': 'm-wt', 'body': json.dumps({'job_id': 'wt', 'token': token_for('other')})}]}
        self.assertEqual(handler.handler(event, None), {'batchItemFailures': [{'itemIdentifier': 'm-wt'}]})
        self.assertEqual(FakeDjango.rejected, ['/internal/jobs/claim/'])
        self.assertEqual(FakeDjango.completed, [])

    def test_a_message_without_a_token_is_retried_without_calling_django(self):
        event = {'Records': [{'messageId': 'm-nt', 'body': json.dumps({'job_id': 'nt'})}]}
        self.assertEqual(handler.handler(event, None), {'batchItemFailures': [{'itemIdentifier': 'm-nt'}]})
        self.assertEqual(FakeDjango.headers_seen, [])

    def test_the_handler_has_no_signing_code_and_needs_no_secret(self):
        self.assertFalse(hasattr(handler, 'sign'))
        self.assertNotIn(SECRET_VAR, os.environ)
        source = open(handler.__file__).read()
        self.assertNotIn(SECRET_VAR, source)
        self.assertNotIn('X-Signature', source)
        self.assertNotIn('hmac', source)

    def test_no_expected_key_is_read_anywhere(self):
        # statically: neither the handler nor the sandbox mentions 'expected' as a string or attribute
        here = os.path.dirname(handler.__file__)
        for name in ('handler.py', 'sandbox.py'):
            tree = ast.parse(open(os.path.join(here, name)).read())
            hits = [n.lineno for n in ast.walk(tree)
                    if (isinstance(n, ast.Constant) and n.value == 'expected')
                    or (isinstance(n, ast.Attribute) and n.attr == 'expected')]
            self.assertEqual(hits, [], name)
        # and at run time: every test dict and the job itself record which keys are read
        read = set()

        class Spy(dict):
            def __getitem__(self, k):
                read.add(k)
                return super().__getitem__(k)

            def get(self, k, default=None):
                read.add(k)
                return super().get(k, default)

        status, claimed = job('sp')
        claimed = Spy({**claimed, 'tests': [Spy(t) for t in claimed['tests']]})
        real_post = handler._post

        def post(path, payload):
            return (status, claimed) if path.endswith('/claim/') else real_post(path, payload)
        with mock.patch.object(handler, '_post', post):
            self.assertEqual(handler.handler(self.event('sp'), None), {'batchItemFailures': []})
        self.assertNotIn('expected', read)
        self.assertEqual(len(FakeDjango.completed), 1)

    def test_body_is_utf8_json_not_ascii_escapes(self):
        # U+FFFD (what invalid UTF-8 output decodes to) costs 3 bytes, not the 6 of "\\ufffd"
        self.assertEqual(handler._encode({'output': '\ufffd'}), '{"output": "\ufffd"}'.encode('utf-8'))

    def assertCompletedOnceUnderTheCap(self):
        self.assertEqual(len(FakeDjango.completed), 1)
        self.assertEqual(FakeDjango.failed, [])  # never an infrastructure failure
        sizes = [n for path, n in FakeDjango.body_sizes if path == '/internal/jobs/complete/']
        self.assertEqual(len(sizes), 1)
        self.assertLess(sizes[0], handler.MAX_BODY_BYTES)
        self.assertLessEqual(handler.MAX_BODY_BYTES, 2_000_000)

    def test_huge_invalid_utf8_output_still_completes_as_a_student_result(self):
        # a real sandbox run: 4 tests, each printing 70,000 bytes of 0xff on stdout and on stderr.
        # Before the size cap this body was ~3.1 MB, Django answered 400 and the job went to the DLQ.
        code = 'import sys\nsys.stdout.buffer.write(b"\\xff" * 70000)\nsys.stderr.buffer.write(b"\\xff" * 70000)'
        tests = [{'id': i, 'input': ''} for i in range(1, 5)]
        FakeDjango.claims['big'] = job('big', code=code, tests=tests)
        FakeDjango.complete_reply = (200, {'status': 'succeeded', 'submission_status': 'failed'})
        self.assertEqual(handler.handler(self.event('big'), None), {'batchItemFailures': []})
        self.assertCompletedOnceUnderTheCap()
        results = FakeDjango.completed[-1]['results']
        self.assertEqual([r['test_id'] for r in results], [1, 2, 3, 4])
        for r in results:
            self.assertFalse(r['timed_out'])
            self.assertTrue(r['output'].startswith('\ufffd'))  # the student's garbage, graded as such

    def test_many_tests_of_control_characters_are_trimmed_with_a_marker(self):
        # control characters are escaped to 6 bytes even with ensure_ascii=False, so the cap must be
        # measured on the encoded body, not counted in characters
        tests = [{'id': i, 'input': ''} for i in range(1, 11)]
        FakeDjango.claims['ctl'] = job('ctl', tests=tests)
        big = {'output': '\x01' * 65536, 'error': '\ufffd' * 65536, 'ms': 1, 'timed_out': False}
        with mock.patch.object(handler.sandbox, 'run', return_value=big):
            self.assertEqual(handler.handler(self.event('ctl'), None), {'batchItemFailures': []})
        self.assertCompletedOnceUnderTheCap()
        for r in FakeDjango.completed[-1]['results']:
            self.assertTrue(r['output'].endswith(handler.TRUNCATED), r['test_id'])
            self.assertTrue(r['error'].endswith(handler.TRUNCATED), r['test_id'])

    def test_every_output_is_trimmed_alike_and_the_body_stays_under_the_cap(self):
        # the handler can't tell a correct output from a wrong one (it never sees expected outputs), so a
        # body over the cap trims every output and error with the same per-field cap
        tests = [{'id': i, 'input': ''} for i in range(1, 21)]
        FakeDjango.claims['all'] = job('all', tests=tests)
        outcomes = iter([{'output': 'y' * 60000 + '\n', 'error': '', 'ms': 1, 'timed_out': False}] +
                        [{'output': '\x01' * 65536, 'error': 'e' * 65536, 'ms': 1, 'timed_out': False}] * 19)
        with mock.patch.object(handler.sandbox, 'run', side_effect=lambda *a: next(outcomes)):
            self.assertEqual(handler.handler(self.event('all'), None), {'batchItemFailures': []})
        self.assertCompletedOnceUnderTheCap()
        results = FakeDjango.completed[-1]['results']
        caps = {len(r['output']) - len(handler.TRUNCATED) for r in results}
        self.assertEqual(len(caps), 1, caps)  # one cap for every output, the plain one included
        cap = caps.pop()
        self.assertLess(cap, 60000)
        self.assertEqual(results[0]['output'], 'y' * cap + handler.TRUNCATED)
        for r in results[1:]:
            self.assertEqual(r['output'], '\x01' * cap + handler.TRUNCATED)
            self.assertEqual(r['error'], 'e' * cap + handler.TRUNCATED)

    def test_halving_stops_as_soon_as_the_body_fits(self):
        # 7 x 65,000 json-escaped characters (6 bytes each) is ~2.7 MB: one halving to 32 K fits
        tests = [{'id': i, 'input': ''} for i in range(1, 8)]
        FakeDjango.claims['half'] = job('half', tests=tests)
        big = {'output': '\x02' * 65000, 'error': '', 'ms': 1, 'timed_out': False}
        with mock.patch.object(handler.sandbox, 'run', return_value=big):
            handler.handler(self.event('half'), None)
        self.assertCompletedOnceUnderTheCap()
        for r in FakeDjango.completed[-1]['results']:
            self.assertEqual(r['output'], '\x02' * (handler.FIRST_CAP_CHARS // 2) + handler.TRUNCATED)

    def test_output_padded_with_json_escaped_whitespace_is_trimmed_like_any_other(self):
        # str.strip() eats \x1c-\x1f but JSON escapes each to 6 bytes: a "4" padded with them must not
        # push the body past Django's limit. With no expected output to compare, the handler can't
        # tell it is a right answer: it is trimmed like everything else (and graded on what is left).
        tests = [{'id': i, 'input': ''} for i in range(1, 8)]
        FakeDjango.claims['pad'] = job('pad', tests=tests)
        padded = {'output': '4\n' + '\x1f' * 65000, 'error': '', 'ms': 1, 'timed_out': False}
        with mock.patch.object(handler.sandbox, 'run', return_value=padded):
            handler.handler(self.event('pad'), None)
        self.assertCompletedOnceUnderTheCap()
        for r in FakeDjango.completed[-1]['results']:
            self.assertTrue(r['output'].startswith('4\n\x1f'), r['test_id'])
            self.assertTrue(r['output'].endswith(handler.TRUNCATED), r['test_id'])
            self.assertLess(len(r['output']), len(padded['output']))

    def test_small_bodies_are_sent_untouched(self):
        FakeDjango.claims['sm'] = job('sm')
        handler.handler(self.event('sm'), None)
        self.assertNotIn(handler.TRUNCATED, json.dumps(FakeDjango.completed[-1]))

    def test_claims_runs_and_completes(self):
        FakeDjango.claims['j1'] = job('j1')
        resp = handler.handler(self.event('j1'), None)
        self.assertEqual(resp, {'batchItemFailures': []})
        done = FakeDjango.completed[-1]
        self.assertEqual((done['job_id'], done['token'], done['lease_token']), ('j1', token_for('j1'), 'tok'))
        self.assertEqual([(r['test_id'], r['output'].strip()) for r in done['results']], [(1, '4'), (2, '10')])
        self.assertEqual(set(done['results'][0]), {'test_id', 'output', 'error', 'ms', 'timed_out'})

    def test_zero_test_cases_complete_with_no_results_never_a_fabricated_pass(self):
        # Django's apply_result turns "no test cases" into submission status 'error'
        FakeDjango.claims['empty'] = job('empty', tests=[])
        FakeDjango.complete_reply = (200, {'status': 'succeeded', 'submission_status': 'error'})
        self.assertEqual(handler.handler(self.event('empty'), None), {'batchItemFailures': []})
        self.assertEqual(FakeDjango.completed[-1]['results'], [])
        self.assertEqual(FakeDjango.failed, [])

    def test_done_gone_dead_are_acknowledged_not_retried(self):
        for jid, code, err in (('d', 409, 'done'), ('g', 410, 'gone'), ('x', 410, 'dead')):
            FakeDjango.claims[jid] = (code, {'error': err})
        self.assertEqual(handler.handler(self.event('d', 'g', 'x'), None), {'batchItemFailures': []})
        self.assertEqual(FakeDjango.completed, [])

    def test_busy_is_retried_later(self):
        FakeDjango.claims['b'] = (409, {'error': 'busy'})
        self.assertEqual(handler.handler(self.event('b'), None), {'batchItemFailures': [{'itemIdentifier': 'm-b'}]})

    def test_unknown_job_and_bad_token_are_retried(self):
        # 404/401 are not "nothing left to do": retry, and SQS's redrive sends it to the DLQ
        FakeDjango.claims['u'] = (404, {'error': 'unknown job'})
        FakeDjango.claims['s'] = (401, {'error': 'bad token'})
        self.assertEqual(handler.handler(self.event('u', 's'), None),
                         {'batchItemFailures': [{'itemIdentifier': 'm-u'}, {'itemIdentifier': 'm-s'}]})

    def test_non_json_error_body_is_a_retry_not_a_crash(self):
        FakeDjango.claims['h'] = (502, b'<html>Bad Gateway</html>')
        self.assertEqual(handler.handler(self.event('h'), None), {'batchItemFailures': [{'itemIdentifier': 'm-h'}]})

    def test_stale_lease_on_complete_is_acknowledged(self):
        FakeDjango.claims['st'] = job('st')
        FakeDjango.complete_reply = (409, {'error': 'stale'})
        self.assertEqual(handler.handler(self.event('st'), None), {'batchItemFailures': []})

    def test_complete_server_error_is_retried(self):
        FakeDjango.claims['c5'] = job('c5')
        FakeDjango.complete_reply = (500, {'error': 'boom'})
        self.assertEqual(handler.handler(self.event('c5'), None), {'batchItemFailures': [{'itemIdentifier': 'm-c5'}]})

    def test_grader_crash_releases_the_lease_and_acks(self):
        # /fail/ put the job back in Django's outbox: the relay owns the retry, so SQS must not retry too
        FakeDjango.claims['cr'] = job('cr')
        with mock.patch.object(handler.sandbox, 'run', side_effect=OSError('disk full')):
            resp = handler.handler(self.event('cr'), None)
        self.assertEqual(resp, {'batchItemFailures': []})
        self.assertEqual((FakeDjango.failed[-1]['job_id'], FakeDjango.failed[-1]['lease_token']), ('cr', 'tok'))
        self.assertIn('disk full', FakeDjango.failed[-1]['error'])
        self.assertEqual(FakeDjango.completed, [])

    def test_a_refused_release_is_retried_by_sqs(self):
        for reply in ((500, {'error': 'boom'}), (409, {'error': 'stale'}), (401, {'error': 'bad token'})):
            FakeDjango.fail_reply = reply
            FakeDjango.claims['rf'] = job('rf')
            with mock.patch.object(handler.sandbox, 'run', side_effect=OSError('disk full')):
                resp = handler.handler(self.event('rf'), None)
            self.assertEqual(resp, {'batchItemFailures': [{'itemIdentifier': 'm-rf'}]}, reply)
            self.assertEqual(FakeDjango.failed[-1]['job_id'], 'rf')

    def test_an_unreachable_release_is_retried_by_sqs(self):
        FakeDjango.claims['ur'] = job('ur')
        real_post = handler._post

        def post(path, payload):
            if path == '/internal/jobs/fail/':
                raise urllib.error.URLError('connection refused')
            return real_post(path, payload)
        with mock.patch.object(handler.sandbox, 'run', side_effect=OSError('disk full')), \
                mock.patch.object(handler, '_post', post):
            resp = handler.handler(self.event('ur'), None)
        self.assertEqual(resp, {'batchItemFailures': [{'itemIdentifier': 'm-ur'}]})

    def test_malformed_message_is_retried_and_does_not_stop_the_batch(self):
        FakeDjango.claims['ok'] = job('ok')
        event = {'Records': [{'messageId': 'm-bad', 'body': 'not json'}] + self.event('ok')['Records']}
        self.assertEqual(handler.handler(event, None), {'batchItemFailures': [{'itemIdentifier': 'm-bad'}]})
        self.assertEqual(FakeDjango.completed[-1]['job_id'], 'ok')

    def test_no_claim_without_time_for_a_worst_case_test(self):
        FakeDjango.claims['nc'] = job('nc')
        resp = handler.handler(self.event('nc'), FakeContext(remaining_ms=handler.CLAIM_MIN_MS - 1))
        self.assertEqual(resp, {'batchItemFailures': [{'itemIdentifier': 'm-nc'}]})
        self.assertEqual(FakeDjango.completed, [])

    def test_first_student_timeout_stops_the_run(self):
        # the code is already too slow: the remaining tests are reported, not run (no 3 x 3 s wait)
        FakeDjango.claims['to'] = job('to', code='import time\ntime.sleep(60)', tests=[
            {'id': 1, 'input': ''}, {'id': 2, 'input': ''}, {'id': 3, 'input': ''}])
        start = time.monotonic()
        resp = handler.handler(self.event('to'), FakeContext(remaining_ms=90_000))
        self.assertLess(time.monotonic() - start, 2 * LIMITS['timeout_s'])
        self.assertEqual(resp, {'batchItemFailures': []})
        results = FakeDjango.completed[-1]['results']
        self.assertEqual([r['test_id'] for r in results], [1, 2, 3])
        self.assertTrue(all(r['timed_out'] for r in results))
        self.assertEqual(results[0]['error'], 'Time limit exceeded')
        self.assertEqual({r['error'] for r in results[1:]}, {'Not run: an earlier test exceeded the time limit'})
        self.assertEqual(FakeDjango.failed, [])

    def test_lambda_budget_exhausted_is_an_infrastructure_failure_not_a_grade(self):
        # no student timeout, but not enough Lambda time for the next test: release the lease (the relay
        # republishes it) and ack the message
        FakeDjango.claims['tb'] = job('tb')
        ctx = FakeContext(remaining_ms=handler.CLAIM_MIN_MS)
        with mock.patch.object(handler, 'RESERVE_MS', handler.CLAIM_MIN_MS):
            resp = handler.handler(self.event('tb'), ctx)
        self.assertEqual(resp, {'batchItemFailures': []})
        self.assertEqual(FakeDjango.completed, [])  # never a failing grade
        self.assertEqual((FakeDjango.failed[-1]['job_id'], FakeDjango.failed[-1]['lease_token']), ('tb', 'tok'))
        self.assertEqual(FakeDjango.failed[-1]['error'], 'grading time budget exhausted')

    def test_budget_running_out_after_a_student_timeout_still_completes(self):
        # (a) wins over (b): once a test timed out the grade is already decided
        FakeDjango.claims['tt'] = job('tt', code='while True: pass')
        ctx = FakeContext(remaining_ms=90_000)
        calls = iter([90_000, 90_000, 1])  # plenty for the claim and test 1, nothing left for test 2
        ctx.get_remaining_time_in_millis = lambda: next(calls, 1)
        resp = handler.handler(self.event('tt'), ctx)
        self.assertEqual(resp, {'batchItemFailures': []})
        self.assertEqual(FakeDjango.failed, [])
        self.assertEqual(FakeDjango.completed[-1]['results'][1]['error'],
                         'Not run: an earlier test exceeded the time limit')

    def test_plenty_of_time_left_runs_every_test(self):
        FakeDjango.claims['pt'] = job('pt')
        handler.handler(self.event('pt'), FakeContext(remaining_ms=90_000))
        self.assertEqual([r['output'].strip() for r in FakeDjango.completed[-1]['results']], ['4', '10'])

    def test_unreachable_django_is_a_retry(self):
        handler.os.environ['CODEMAS_API_URL'] = 'http://127.0.0.1:9'
        try:
            self.assertEqual(handler.handler(self.event('z'), None), {'batchItemFailures': [{'itemIdentifier': 'm-z'}]})
        finally:
            handler.os.environ['CODEMAS_API_URL'] = f'http://127.0.0.1:{self.server.server_port}'


class SelfCheckLogTest(unittest.TestCase):
    def test_cold_start_logs_the_sandbox_selfcheck_as_one_json_line(self):
        with mock.patch.object(handler.sandbox, 'egress_blocked', return_value=True), \
                mock.patch('builtins.print') as p:
            handler._selfcheck()
        p.assert_called_once()
        self.assertEqual(json.loads(p.call_args.args[0]), {'event': 'sandbox_selfcheck', 'egress_blocked': True})

    def test_a_crashing_selfcheck_logs_null_and_does_not_break_the_import(self):
        with mock.patch.object(handler.sandbox, 'egress_blocked', side_effect=OSError('boom')), \
                mock.patch('builtins.print') as p:
            handler._selfcheck()
        self.assertEqual(json.loads(p.call_args.args[0]), {'event': 'sandbox_selfcheck', 'egress_blocked': None})


@unittest.skipUnless(LINUX, '/proc is Linux-only (Lambda)')
class ParentSecretsTest(unittest.TestCase):
    """The handler's environment holds the role's AWS credentials (no signing secret any more)."""

    def test_student_code_cannot_read_the_handler_environ(self):
        code = 'import os\nprint(open(f"/proc/{os.getppid()}/environ", "rb").read())'
        r = handler.sandbox.run('python', code, '', LIMITS)
        self.assertNotIn('PATH=', r['output'])
        self.assertIn('PermissionError', r['error'])

if __name__ == '__main__':
    unittest.main()
