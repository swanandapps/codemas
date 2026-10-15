import json
import uuid
from datetime import timedelta
from unittest import mock

from django.db import transaction
from django.test import TestCase, override_settings
from django.utils import timezone

from accounts.models import User
from exams.models import Exam, Question, TestCase as QTest
from jobs.models import Job
from jobs.services import enqueue
from jobs.signing import job_token
from results.models import Result
from submissions.models import Submission

SECRET = 'test-secret'


@override_settings(JOB_SIGNING_SECRET=SECRET)
class InternalApiTest(TestCase):
    def setUp(self):
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.student = User.objects.create_user(username='s', password='pw', role='student', cohort='C')
        exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60, is_active=True,
                                   start_time=timezone.now() - timedelta(hours=1),
                                   end_time=timezone.now() + timedelta(hours=1))
        self.q = Question.objects.create(exam=exam, title='Q', description='d', difficulty='easy')
        self.t1 = QTest.objects.create(question=self.q, input_data='1', expected_output='2')
        self.t2 = QTest.objects.create(question=self.q, input_data='2', expected_output='3')
        self.sub = Submission.objects.create(student=self.student, exam=exam, question=self.q,
                                             code='print(int(input())+1)', language='python', attempt_number=1)
        with transaction.atomic():
            self.job = enqueue(Job.KIND_EXECUTE, self.sub.id)
        Job.objects.filter(pk=self.job.pk).update(status='queued')

    def post(self, path, payload):
        """payload gets this job's token unless it already has a 'token' key (None: leave it out)."""
        payload = dict(payload)
        if 'token' not in payload:
            payload['token'] = job_token(payload.get('job_id', self.job.id))
        elif payload['token'] is None:
            del payload['token']
        return self.client.post(path, data=json.dumps(payload).encode(), content_type='application/json')

    def claim(self, **extra):
        return self.post('/internal/jobs/claim/', {'job_id': str(self.job.id), **extra})

    def complete(self, lease, outputs, **extra):
        results = [{'test_id': tid, 'output': out, 'error': '', 'ms': 5, 'timed_out': False}
                   for tid, out in outputs]
        return self.post('/internal/jobs/complete/', {'job_id': str(self.job.id), 'lease_token': lease,
                                                       'results': results, **extra})

    # ── claim ──
    def test_claim_returns_code_and_tests_and_leases_the_job(self):
        r = self.claim()
        self.assertEqual(r.status_code, 200)
        data = r.json()
        self.assertEqual(data['code'], 'print(int(input())+1)')
        self.assertEqual([t['id'] for t in data['tests']], [self.t1.id, self.t2.id])
        self.assertEqual(data['tests'], [{'id': self.t1.id, 'input': '1'}, {'id': self.t2.id, 'input': '2'}])
        self.assertEqual(data['limits']['timeout_s'], 10)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'running')
        self.assertEqual(self.job.attempt, 1)
        self.assertEqual(str(self.job.lease_token), data['lease_token'])
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, 'running')

    def test_second_claim_while_leased_is_busy(self):
        self.claim()
        self.assertEqual(self.claim().json(), {'error': 'busy'})

    def test_claim_after_lease_expiry_gets_a_new_token(self):
        first = self.claim().json()['lease_token']
        Job.objects.filter(pk=self.job.pk).update(lease_expires_at=timezone.now() - timedelta(seconds=1))
        second = self.claim().json()['lease_token']
        self.assertNotEqual(first, second)

    def test_claim_on_terminal_job_is_done(self):
        Job.objects.filter(pk=self.job.pk).update(status='succeeded')
        r = self.claim()
        self.assertEqual((r.status_code, r.json()), (409, {'error': 'done'}))

    def test_claim_past_max_attempts_marks_dead(self):
        Job.objects.filter(pk=self.job.pk).update(attempt=3)
        r = self.claim()
        self.assertEqual((r.status_code, r.json()), (410, {'error': 'dead'}))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'dead')
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, 'error')

    def test_claim_for_deleted_submission_is_gone(self):
        self.sub.delete()
        r = self.claim()
        self.assertEqual((r.status_code, r.json()), (410, {'error': 'gone'}))
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'failed')

    # ── per-job token ──
    def test_a_good_token_claims(self):
        self.assertEqual(self.claim(token=job_token(self.job.id)).status_code, 200)

    def test_bad_missing_or_another_jobs_token_is_401_and_claims_nothing(self):
        other = str(uuid.uuid4())
        with self.settings(JOB_SIGNING_SECRET='wrong'):
            forged = job_token(self.job.id)
        for token in (forged, job_token(other), None, '', 'x' * 64, 42):
            with self.subTest(token=token):
                r = self.claim(token=token)
                self.assertEqual((r.status_code, r.json()), (401, {'error': 'bad token'}))
        self.job.refresh_from_db()
        self.assertEqual((self.job.status, self.job.attempt), ('queued', 0))

    def test_old_signature_headers_are_no_substitute_for_the_token(self):
        # the old X-Timestamp/X-Signature scheme is gone: headers alone authenticate nothing
        body = json.dumps({'job_id': str(self.job.id)}).encode()
        r = self.client.post('/internal/jobs/claim/', data=body, content_type='application/json',
                             HTTP_X_TIMESTAMP='1800000000', HTTP_X_SIGNATURE='sha256=' + '0' * 64)
        self.assertEqual(r.status_code, 401)

    def test_claim_response_carries_no_expected_output(self):
        data = self.claim().json()
        self.assertNotIn('expected', json.dumps(data))
        for t in data['tests']:
            self.assertEqual(set(t), {'id', 'input'})

    def test_complete_needs_both_the_job_token_and_the_lease(self):
        lease = self.claim().json()['lease_token']
        outputs = [(self.t1.id, '2'), (self.t2.id, '3')]
        r = self.complete(lease, outputs, token=job_token(uuid.uuid4()))  # right lease, wrong token
        self.assertEqual(r.status_code, 401)
        r = self.complete(lease, outputs, token=None)  # right lease, no token
        self.assertEqual(r.status_code, 401)
        r = self.complete(str(uuid.uuid4()), outputs)  # right token, wrong lease
        self.assertEqual((r.status_code, r.json()), (409, {'error': 'stale'}))
        self.assertEqual(Result.objects.filter(submission=self.sub).count(), 0)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, 'running')
        r = self.complete(lease, outputs)  # both
        self.assertEqual(r.json(), {'status': 'succeeded', 'submission_status': 'passed'})

    def test_fail_needs_both_the_job_token_and_the_lease(self):
        lease = self.claim().json()['lease_token']
        body = {'job_id': str(self.job.id), 'lease_token': lease, 'error': 'boom'}
        self.assertEqual(self.post('/internal/jobs/fail/', {**body, 'token': 'nope'}).status_code, 401)
        self.assertEqual(self.post('/internal/jobs/fail/', {**body, 'lease_token': str(uuid.uuid4())}).status_code, 409)
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'running')
        self.assertEqual(self.post('/internal/jobs/fail/', body).status_code, 200)

    def test_a_token_for_one_job_cannot_complete_another(self):
        lease = self.claim().json()['lease_token']
        sub2 = Submission.objects.create(student=self.student, exam=self.sub.exam, question=self.q,
                                         code='print(1)', language='python', attempt_number=2)
        with transaction.atomic():
            other = enqueue(Job.KIND_EXECUTE, sub2.id)
        r = self.complete(lease, [(self.t1.id, '2'), (self.t2.id, '3')], token=job_token(other.id))
        self.assertEqual(r.status_code, 401)

    def test_unknown_job_is_404(self):
        r = self.post('/internal/jobs/claim/', {'job_id': str(uuid.uuid4())})
        self.assertEqual(r.status_code, 404)

    def test_malformed_job_id_is_400(self):
        for token in (job_token('not-a-uuid'), None):  # 400 whatever the token
            r = self.post('/internal/jobs/claim/', {'job_id': 'not-a-uuid', 'token': token})
            self.assertEqual(r.status_code, 400)

    def test_malformed_body_is_400(self):
        for body in (b'not json', b'[1, 2]', b'"x"', b'{}'):
            r = self.client.post('/internal/jobs/claim/', data=body, content_type='application/json')
            self.assertEqual(r.status_code, 400, body)

    # ── complete: what the Lambda's size cap relies on ──
    def post_raw(self, path, body):
        return self.client.post(path, data=body, content_type='application/json')

    def test_complete_accepts_a_utf8_body_and_grades_garbage_as_failed(self):
        # the handler sends json.dumps(..., ensure_ascii=False) as UTF-8; U+FFFD is the student's invalid output
        token = self.claim().json()['lease_token']
        garbage = '�' * 65536 + '\n[output truncated]'
        results = [{'test_id': t.id, 'output': garbage, 'error': garbage, 'ms': 1, 'timed_out': False}
                   for t in (self.t1, self.t2)]
        body = json.dumps({'job_id': str(self.job.id), 'token': job_token(self.job.id), 'lease_token': token,
                           'results': results}, ensure_ascii=False).encode('utf-8')
        self.assertGreater(len(body), 700_000)  # 3 bytes per U+FFFD
        r = self.post_raw('/internal/jobs/complete/', body)
        self.assertEqual(r.json(), {'status': 'succeeded', 'submission_status': 'failed'})
        self.assertTrue(Result.objects.get(submission=self.sub, test_case=self.t1).actual_output.startswith('�'))

    def test_a_body_over_django_upload_limit_is_400(self):
        # DATA_UPLOAD_MAX_MEMORY_SIZE (default 2.5 MB) is why lambda/exec/handler.py caps at 2,000,000 bytes
        from django.conf import settings
        self.assertGreater(settings.DATA_UPLOAD_MAX_MEMORY_SIZE, 2_000_000)
        token = self.claim().json()['lease_token']
        body = json.dumps({'job_id': str(self.job.id), 'token': job_token(self.job.id), 'lease_token': token,
                           'results': [{'test_id': self.t1.id, 'output': 'x' * settings.DATA_UPLOAD_MAX_MEMORY_SIZE}]})
        self.assertEqual(self.post_raw('/internal/jobs/complete/', body.encode()).status_code, 400)

    # ── complete ──
    def test_complete_records_results_and_status(self):
        token = self.claim().json()['lease_token']
        r = self.complete(token, [(self.t1.id, '2\n'), (self.t2.id, '4')])
        self.assertEqual(r.json(), {'status': 'succeeded', 'submission_status': 'failed'})
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, 'failed')
        self.assertEqual(self.sub.execution_time_ms, 10)
        passed = dict(Result.objects.filter(submission=self.sub).values_list('test_case_id', 'passed'))
        self.assertEqual(passed, {self.t1.id: True, self.t2.id: False})
        self.job.refresh_from_db()
        self.assertEqual(self.job.status, 'succeeded')
        self.assertIsNotNone(self.job.finished_at)

    def test_complete_with_stale_token_writes_nothing(self):
        self.claim()
        r = self.complete(str(uuid.uuid4()), [(self.t1.id, '2'), (self.t2.id, '3')])
        self.assertEqual((r.status_code, r.json()), (409, {'error': 'stale'}))
        self.assertEqual(Result.objects.filter(submission=self.sub).count(), 0)

    def test_second_complete_is_a_no_op(self):
        token = self.claim().json()['lease_token']
        self.complete(token, [(self.t1.id, '2'), (self.t2.id, '3')])
        r = self.complete(token, [(self.t1.id, 'x'), (self.t2.id, 'y')])
        self.assertEqual(r.status_code, 409)
        self.sub.refresh_from_db()
        self.assertEqual(self.sub.status, 'passed')

    def test_complete_runs_the_legacy_side_effects_after_commit(self):
        token = self.claim().json()['lease_token']
        with mock.patch('codemas.notifications.notify_result_ready') as notify, \
                mock.patch('ai.tasks.score_rubric.delay') as rubric, \
                mock.patch('ai.tasks.generate_hint.delay') as hint, \
                self.captureOnCommitCallbacks(execute=True):
            self.complete(token, [(self.t1.id, '2'), (self.t2.id, 'wrong')])
        self.sub.refresh_from_db()
        self.assertNotEqual(self.sub.normalized_code, '')
        notify.assert_called_once()
        rubric.assert_called_once_with(self.sub.id)
        hint.assert_called_once_with(self.sub.id)  # failed → hint

    def test_passing_submission_gets_no_hint(self):
        token = self.claim().json()['lease_token']
        with mock.patch('codemas.notifications.notify_result_ready'), \
                mock.patch('ai.tasks.score_rubric.delay') as rubric, \
                mock.patch('ai.tasks.generate_hint.delay') as hint, \
                self.captureOnCommitCallbacks(execute=True):
            self.complete(token, [(self.t1.id, '2'), (self.t2.id, '3')])
        rubric.assert_called_once_with(self.sub.id)
        hint.assert_not_called()

    def test_question_without_tests_is_an_error_not_a_pass(self):
        QTest.objects.filter(question=self.q).delete()
        token = self.claim().json()['lease_token']
        r = self.complete(token, [])
        self.assertEqual(r.json()['submission_status'], 'error')

    # ── fail ──
    def test_fail_releases_the_lease_for_an_immediate_retry(self):
        token = self.claim().json()['lease_token']
        self.post('/internal/jobs/fail/', {'job_id': str(self.job.id), 'lease_token': token, 'error': 'boom'})
        self.job.refresh_from_db()
        # back to the outbox: the relay republishes it on its next tick, in either transport
        self.assertEqual((self.job.status, self.job.last_error), ('pending', 'boom'))
        self.assertEqual(self.job.attempt, 1)  # the failed try still counts
        self.assertIsNone(self.job.lease_token)
        self.assertIsNone(self.job.lease_expires_at)
        self.assertEqual(self.claim().status_code, 200)
