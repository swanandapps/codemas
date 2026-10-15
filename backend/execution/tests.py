from datetime import timedelta
from unittest import mock

from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from exams.models import Exam, Question, TestCase as QTest
from submissions.models import Submission


class LegacyTaskTest(TestCase):
    def test_grades_without_publishing_to_redis(self):
        # the SSE stream that listened on submission:<id> is gone; the exam page polls /status/
        trainer = User.objects.create_user(username='tr', password='pw', role='trainer')
        student = User.objects.create_user(username='st', password='pw', role='student', cohort='C')
        exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60, is_active=True,
                                   start_time=timezone.now() - timedelta(hours=1),
                                   end_time=timezone.now() + timedelta(hours=1))
        q = Question.objects.create(exam=exam, title='Q', description='d', difficulty='easy')
        QTest.objects.create(question=q, input_data='1', expected_output='2')
        sub = Submission.objects.create(student=student, exam=exam, question=q, code='print(int(input())+1)',
                                        language='python', attempt_number=1)
        from execution import tasks
        with mock.patch('redis.Redis.from_url', side_effect=AssertionError('no Redis publish expected')), \
                mock.patch('codemas.notifications.notify_result_ready'), \
                mock.patch('ai.tasks.score_rubric'), mock.patch('ai.tasks.generate_hint'):
            tasks.execute_submission(sub.id)
        sub.refresh_from_db()
        self.assertEqual(sub.status, 'passed')
        self.assertFalse(hasattr(tasks, 'docker'))  # web no longer imports the docker SDK
