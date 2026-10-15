"""The whole local pipeline: API -> outbox row -> relay tick -> LocalTransport -> the real Lambda handler
(lambda/exec/handler.py) -> claim/complete with the per-job token against a live Django server -> graded submission.
The handler process never has JOB_SIGNING_SECRET: only the relay (this process's settings) mints tokens."""
import json
import os
import shutil
from datetime import timedelta
from unittest import mock

from django.test import LiveServerTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, ExamEnrollment, Question, TestCase as QTest
from jobs.models import MAX_ATTEMPTS, Job
from jobs.relay import sweep_stuck, tick
from jobs.services import claim, fail
from jobs.transports import LocalTransport
from submissions.models import Submission

LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(JOB_SIGNING_SECRET='e2e-secret', PIPELINE_LANGUAGES={'python', 'javascript'}, CACHES=LOCMEM,
                   JOB_TRANSPORT='local')
class LocalPipelineE2E(LiveServerTestCase):
    def setUp(self):
        env = mock.patch.dict(os.environ, {'CODEMAS_API_URL': self.live_server_url})
        env.start()
        self.addCleanup(env.stop)
        os.environ.pop('JOB_SIGNING_SECRET', None)  # the handler must work without it
        # grading side effects: keep them off the dev Redis / Celery worker, which would act on the dev DB
        self.mocks = {}
        for target in ('codemas.notifications.notify_result_ready', 'ai.tasks.score_rubric.delay',
                       'ai.tasks.generate_hint.delay'):
            p = mock.patch(target)
            self.mocks[target] = p.start()
            self.addCleanup(p.stop)
        trainer = User.objects.create_user(username='tr', password='pw', role='trainer')
        self.student = User.objects.create_user(username='st', password='pw', role='student', cohort='C')
        exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60, is_active=True,
                                   start_time=timezone.now() - timedelta(hours=1), end_time=timezone.now() + timedelta(hours=1))
        ExamEnrollment.objects.create(exam=exam, student=self.student)
        self.q = Question.objects.create(exam=exam, title='Double', description='d', difficulty='easy')
        QTest.objects.create(question=self.q, input_data='2', expected_output='4')
        QTest.objects.create(question=self.q, input_data='5', expected_output='10')
        self.api = APIClient(); self.api.force_authenticate(self.student)

    def submit(self, language='python', code='print(int(input()) * 2)'):
        resp = self.api.post('/api/submissions/create/', {'question': self.q.id, 'code': code, 'language': language},
                             format='json')
        self.assertEqual(resp.status_code, 201, resp.data)
        return resp.data['id']

    def relay(self, expect=1, transport=None):
        transport = transport or LocalTransport(workers=1, redeliver_delays=(0.2, 0.2))
        self.assertEqual(tick(transport), expect)
        transport.close(wait=True)  # wait for the handler thread

    def status(self, sid):
        return self.api.get(f'/api/submissions/{sid}/status/').data

    def grade(self, language, code):
        sid = self.submit(language, code)
        self.relay()
        return self.status(sid)

    def test_python_submission_is_graded_end_to_end(self):
        data = self.grade('python', 'print(int(input()) * 2)')
        self.assertEqual((data['status'], data['job']['status'], data['results_ready']), ('passed', 'succeeded', True))
        self.assertEqual(data['job']['attempt'], 1)

    def test_the_handler_sends_the_relays_token_and_never_sees_expected_outputs(self):
        from jobs.signing import job_token
        sid = self.submit()
        transport = LocalTransport(workers=1, redeliver_delays=(0.2, 0.2))
        real_post, sent, claimed = transport.handler._post, [], []

        def spy(path, payload):
            sent.append((path, payload if isinstance(payload, dict) else json.loads(payload)))
            status, out = real_post(path, payload)
            if path.endswith('/claim/'):
                claimed.append(out)
            return status, out
        with mock.patch.object(transport.handler, '_post', spy):
            self.relay(transport=transport)
        token = job_token(Job.objects.get(subject_id=sid).pk)
        self.assertEqual([(p, b['token']) for p, b in sent],
                         [('/internal/jobs/claim/', token), ('/internal/jobs/complete/', token)])
        self.assertNotIn('expected', json.dumps(claimed))
        self.assertNotIn('JOB_SIGNING_SECRET', os.environ)
        self.assertEqual(self.status(sid)['status'], 'passed')

    def test_wrong_answer_fails(self):
        data = self.grade('python', 'print(int(input()) + 2)')
        self.assertEqual((data['status'], data['job']['status']), ('failed', 'succeeded'))

    def test_javascript_submission_is_graded_end_to_end(self):
        if not shutil.which('node'):
            self.skipTest('node not installed')
        code = "const n=Number(require('fs').readFileSync(0,'utf8')); console.log(n*2)"
        self.assertEqual(self.grade('javascript', code)['status'], 'passed')

    def test_a_deleted_submission_ends_gone_and_is_not_retried(self):
        sid = self.submit()
        job = Job.objects.get(subject_id=sid)
        Submission.objects.filter(pk=sid).delete()
        self.relay()
        job.refresh_from_db()
        self.assertEqual((job.status, job.last_error), ('failed', 'subject deleted'))
        # terminal: neither the sweep nor the next tick touches it again
        self.assertEqual(sweep_stuck(now=timezone.now() + timedelta(days=1)), {'requeued': 0, 'dead': 0})
        self.relay(expect=0)

    def test_a_job_released_by_fail_is_regraded_by_the_next_tick(self):
        sid = self.submit()
        tick(_Null())  # published, then a handler claims it and gives up
        job = Job.objects.get(subject_id=sid)
        claimed, _ = claim(job.pk)
        fail(job.pk, claimed.lease_token, 'grader crashed')
        job.refresh_from_db()
        self.assertEqual(job.status, 'pending')
        with mock.patch('jobs.relay.sweep_stuck') as sweep:  # no sweep involved: the next tick picks it up
            self.relay()
        sweep.assert_not_called()
        data = self.status(sid)
        self.assertEqual((data['status'], data['job']['status'], data['job']['attempt']), ('passed', 'succeeded', 2))

    def test_a_handler_failure_is_redelivered_and_graded_once(self):
        """The first delivery can't reach Django; LocalTransport redelivers it like SQS would."""
        sid = self.submit()
        transport = LocalTransport(workers=1, redeliver_delays=(0.2, 0.2))
        real_post, calls = transport.handler._post, []

        def flaky_post(path, payload):
            calls.append(path)
            if len(calls) == 1:
                raise ConnectionError('django unreachable')
            return real_post(path, payload)
        with mock.patch.object(transport.handler, '_post', flaky_post):
            self.relay(transport=transport)
        data = self.status(sid)
        self.assertEqual((data['status'], data['job']['status'], data['job']['attempt']), ('passed', 'succeeded', 1))
        self.assertEqual(calls, ['/internal/jobs/claim/', '/internal/jobs/claim/', '/internal/jobs/complete/'])

    def test_a_grader_crash_is_released_acked_and_regraded_by_the_next_tick(self):
        """/fail/ succeeds, so the handler acks: no redelivery; the job is pending and the relay retries it."""
        sid = self.submit()
        transport = LocalTransport(workers=1, redeliver_delays=(0.2, 0.2))
        sandbox = transport.handler.sandbox
        real_run, calls = sandbox.run, []

        def flaky_run(*args):
            calls.append(1)
            if len(calls) == 1:
                raise OSError('disk full')
            return real_run(*args)
        with mock.patch.object(sandbox, 'run', flaky_run), mock.patch.object(transport, '_handle_once',
                                                                             wraps=transport._handle_once) as deliveries:
            self.relay(transport=transport)
            self.assertEqual(deliveries.call_count, 1)  # acked: not redelivered
            job = Job.objects.get(subject_id=sid)
            self.assertEqual((job.status, job.attempt), ('pending', 1))
            self.assertIn('disk full', job.last_error)
            self.relay()  # the next tick
        data = self.status(sid)
        self.assertEqual((data['status'], data['job']['status'], data['job']['attempt']), ('passed', 'succeeded', 2))

    def test_duplicate_deliveries_never_grade_twice(self):
        sid = self.submit()
        transport = LocalTransport(workers=3, redeliver_delays=(0.2, 0.2))
        job = Job.objects.get(subject_id=sid)
        self.assertEqual(tick(transport), 1)
        transport.publish(job)  # the same message twice more, at once
        transport.publish(job)
        transport.close(wait=True)
        data = self.status(sid)
        self.assertEqual((data['status'], data['job']['status'], data['job']['attempt']), ('passed', 'succeeded', 1))
        self.mocks['codemas.notifications.notify_result_ready'].assert_called_once()  # one grading commit
        self.assertEqual(Submission.objects.get(pk=sid).results.count(), 2)

    def test_a_job_whose_lease_expired_is_swept_back_and_graded(self):
        sid = self.submit()
        tick(_Null())
        job = Job.objects.get(subject_id=sid)
        claimed, _ = claim(job.pk)  # a handler took it and died without calling /fail/
        self.assertEqual(sweep_stuck(now=claimed.lease_expires_at + timedelta(seconds=1)), {'requeued': 1, 'dead': 0})
        self.relay()
        data = self.status(sid)
        self.assertEqual((data['status'], data['job']['status'], data['job']['attempt']), ('passed', 'succeeded', 2))

    def test_a_job_out_of_attempts_dies_through_the_handler_and_frees_the_attempt(self):
        sid = self.submit()
        Job.objects.filter(subject_id=sid).update(attempt=MAX_ATTEMPTS)
        self.relay()
        data = self.status(sid)
        self.assertEqual((data['status'], data['job']['status']), ('error', 'dead'))
        self.assertFalse(Job.objects.filter(subject_id=sid, status__in=Job.ACTIVE).exists())


class _Null:
    """A transport that accepts and drops the message, like SQS before any consumer reads it."""

    def publish(self, job):
        pass
