from django.test import TestCase

# Create your tests here.
import threading
from datetime import timedelta

from django.db import connection
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, ExamEnrollment, Question, TestCase as QTest
from jobs.models import Job
from submissions.models import Submission

# keep DRF throttle counters out of the dev Redis (the create view is throttled)
LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


def make_world(enroll=True):
    trainer = User.objects.create_user(username='tr', password='pw', role='trainer')
    student = User.objects.create_user(username='st', password='pw', role='student', cohort='C')
    exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60, is_active=True,
                               start_time=timezone.now() - timedelta(hours=1), end_time=timezone.now() + timedelta(hours=1))
    if enroll:
        ExamEnrollment.objects.create(exam=exam, student=student)
    q = Question.objects.create(exam=exam, title='Q', description='d', difficulty='easy')
    QTest.objects.create(question=q, input_data='1', expected_output='2')
    return trainer, student, q


@override_settings(PIPELINE_LANGUAGES={'python', 'javascript'}, CACHES=LOCMEM)
class PipelineCreateTest(TestCase):
    def setUp(self):
        self.trainer, self.student, self.q = make_world()
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def submit(self, language='python'):
        return self.api.post('/api/submissions/create/', {'question': self.q.id, 'code': 'print(2)', 'language': language},
                             format='json')

    def test_python_submission_writes_an_outbox_job_in_the_same_transaction(self):
        r = self.submit()
        self.assertEqual(r.status_code, 201)
        job = Job.objects.get(subject_id=r.data['id'])
        self.assertEqual((job.kind, job.status), (Job.KIND_EXECUTE, 'pending'))

    def test_language_outside_the_pipeline_uses_the_legacy_path_and_no_job(self):
        # PIPELINE_LANGUAGES="" is the documented rollback: Python goes back to Celery
        from unittest import mock
        with self.settings(PIPELINE_LANGUAGES=set()), mock.patch('submissions.views.execute_submission') as legacy:
            with self.captureOnCommitCallbacks(execute=True):
                r = self.submit(language='python')
        self.assertFalse(Job.objects.filter(subject_id=r.data['id']).exists())
        legacy.delay.assert_called_once_with(r.data['id'])

    def test_cpp_and_java_are_rejected(self):
        for language in ('cpp', 'java'):
            r = self.submit(language=language)
            self.assertEqual(r.status_code, 400)
            self.assertIn('language', r.data)
        self.assertFalse(Submission.objects.exists())

    def test_status_endpoint_reports_job_progress(self):
        sid = self.submit().data['id']
        data = self.api.get(f'/api/submissions/{sid}/status/').data
        self.assertEqual(data['status'], 'pending')
        self.assertEqual(data['job']['status'], 'pending')
        self.assertFalse(data['results_ready'])

    def test_status_endpoint_is_private(self):
        sid = self.submit().data['id']
        other = User.objects.create_user(username='o', password='pw', role='student', cohort='C')
        api = APIClient(); api.force_authenticate(other)
        self.assertEqual(api.get(f'/api/submissions/{sid}/status/').status_code, 403)

    def test_dead_job_does_not_use_up_an_attempt(self):
        sid = self.submit().data['id']
        Job.objects.filter(subject_id=sid).update(status='dead')
        Submission.objects.filter(pk=sid).update(status='error')
        self.submit(); self.submit()
        r = self.submit()   # 4 submissions, but the dead one is not counted against max_attempts=3
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['attempt_number'], 4)

    def test_error_submission_without_a_dead_job_does_not_use_up_an_attempt(self):
        # e.g. the question had no test cases: the job succeeded but the submission is 'error'
        sid = self.submit().data['id']
        Job.objects.filter(subject_id=sid).update(status='succeeded')
        Submission.objects.filter(pk=sid).update(status='error')
        self.submit(); self.submit()
        r = self.submit()
        self.assertEqual(r.status_code, 201)
        self.assertEqual(r.data['attempt_number'], 4)

    def test_a_concurrent_save_is_409_with_a_message_the_page_can_end_with_a_period(self):
        # ExamTakeView shows `Your code wasn't submitted: ${error}.`, so the message has no final period
        from unittest import mock
        from django.db import IntegrityError
        with mock.patch('jobs.services.enqueue', side_effect=IntegrityError):
            r = self.submit()
        self.assertEqual(r.status_code, 409)
        self.assertEqual(r.data['error'], 'Another submission for this question is being saved. Try again')

    def test_the_sse_stream_is_gone(self):
        # nothing published to it for pipeline submissions, so each open stream pinned a web thread forever
        sid = self.submit().data['id']
        self.assertEqual(self.api.get(f'/api/submissions/{sid}/stream/').status_code, 404)

    def test_passed_and_failed_submissions_still_use_up_attempts(self):
        ids = [self.submit().data['id'] for _ in range(3)]
        Submission.objects.filter(pk=ids[0]).update(status='passed')
        Submission.objects.filter(pk=ids[1]).update(status='failed')
        r = self.submit()   # third is still pending: 3 counted against max_attempts=3
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data['error'], 'Max attempts reached')


@override_settings(PIPELINE_LANGUAGES={'python', 'javascript'}, CACHES=LOCMEM)
class EnrollmentGuardTest(TestCase):
    """A student can only submit to an exam they are enrolled in."""

    def setUp(self):
        self.trainer, self.student, self.q = make_world(enroll=False)
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def submit(self):
        return self.api.post('/api/submissions/create/', {'question': self.q.id, 'code': 'print(2)', 'language': 'python'},
                             format='json')

    def test_unenrolled_student_gets_403_and_nothing_is_created(self):
        r = self.submit()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data, {'error': "You're not enrolled in this exam."})
        self.assertFalse(Submission.objects.exists())
        self.assertFalse(Job.objects.exists())

    def test_unenrolled_student_with_a_legacy_language_creates_nothing_either(self):
        from unittest import mock
        with self.settings(PIPELINE_LANGUAGES=set()), mock.patch('submissions.views.execute_submission') as legacy:
            with self.captureOnCommitCallbacks(execute=True):
                r = self.api.post('/api/submissions/create/', {'question': self.q.id, 'code': 'x', 'language': 'python'},
                                  format='json')
        self.assertEqual(r.status_code, 403)
        self.assertFalse(Submission.objects.exists())
        legacy.delay.assert_not_called()

    def test_enrolled_student_gets_201(self):
        ExamEnrollment.objects.create(exam=self.q.exam, student=self.student)
        r = self.submit()
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Job.objects.filter(subject_id=r.data['id']).exists())

    def test_enrolment_in_another_exam_does_not_count(self):
        other = Exam.objects.create(title='Other', created_by=self.trainer, is_active=True)
        ExamEnrollment.objects.create(exam=other, student=self.student)
        self.assertEqual(self.submit().status_code, 403)


@override_settings(PIPELINE_LANGUAGES={'python', 'javascript'}, CACHES=LOCMEM)
class ExamWindowGuardTest(TestCase):
    """A student can only submit while the exam is open: active and inside [start_time, end_time)."""

    def setUp(self):
        self.trainer, self.student, self.q = make_world()
        self.exam = self.q.exam
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def submit(self):
        return self.api.post('/api/submissions/create/', {'question': self.q.id, 'code': 'print(2)', 'language': 'python'},
                             format='json')

    def set_exam(self, **fields):
        Exam.objects.filter(pk=self.exam.pk).update(**fields)

    def assert_refused(self, message):
        r = self.submit()
        self.assertEqual(r.status_code, 403)
        self.assertEqual(r.data, {'error': message})
        self.assertFalse(Submission.objects.exists())
        self.assertFalse(Job.objects.exists())

    def test_after_end_time_is_403_and_nothing_is_created(self):
        now = timezone.now()
        self.set_exam(start_time=now - timedelta(hours=2), end_time=now - timedelta(seconds=1))
        self.assert_refused('This exam has ended.')

    def test_before_start_time_is_403(self):
        now = timezone.now()
        self.set_exam(start_time=now + timedelta(minutes=5), end_time=now + timedelta(hours=1))
        self.assert_refused("This exam hasn't started yet.")

    def test_inactive_exam_is_403(self):
        self.set_exam(is_active=False)
        self.assert_refused("This exam isn't open.")

    def test_open_exam_is_201(self):
        r = self.submit()
        self.assertEqual(r.status_code, 201)
        self.assertTrue(Submission.objects.filter(pk=r.data['id']).exists())

    def test_active_exam_without_times_is_open(self):
        self.set_exam(start_time=None, end_time=None)
        self.assertEqual(self.submit().status_code, 201)


@override_settings(PIPELINE_LANGUAGES={'python'}, CACHES=LOCMEM)
class AttemptRaceTest(TransactionTestCase):
    def test_two_concurrent_submits_for_the_last_attempt_only_one_wins(self):
        _, student, q = make_world()
        for n in (1, 2):
            Submission.objects.create(student=student, exam=q.exam, question=q, code='x', language='python', attempt_number=n)
        codes = []

        def go():
            api = APIClient(); api.force_authenticate(student)
            codes.append(api.post('/api/submissions/create/', {'question': q.id, 'code': 'print(2)', 'language': 'python'},
                                  format='json').status_code)
            connection.close()

        threads = [threading.Thread(target=go) for _ in range(2)]
        [t.start() for t in threads]; [t.join() for t in threads]
        self.assertEqual(sorted(codes), [201, 403])
