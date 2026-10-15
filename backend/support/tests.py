from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, Question
from plagiarism.models import BehaviouralFlag
from submissions.models import Submission


class ExamOpsTest(TestCase):

    def setUp(self):
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.api = APIClient()
        self.api.force_authenticate(self.trainer)

    def ops(self, exam):
        return self.api.get(f'/api/support/exam/{exam.id}/ops/').data

    def test_live_exam_without_end_time_is_live_with_no_countdown(self):
        exam = Exam.objects.create(title='Open', created_by=self.trainer, is_active=True)
        info = self.ops(exam)['exam']
        self.assertTrue(info['is_live'])
        self.assertEqual(info['status'], 'live')
        self.assertIsNone(info['seconds_remaining'])

    def test_live_exam_with_end_time_counts_down(self):
        exam = Exam.objects.create(title='Timed', created_by=self.trainer, is_active=True,
                                   end_time=timezone.now() + timedelta(minutes=30))
        info = self.ops(exam)['exam']
        self.assertTrue(info['is_live'])
        self.assertTrue(1700 < info['seconds_remaining'] <= 1800)

    def test_closed_exam_is_ended(self):
        exam = Exam.objects.create(title='Open', created_by=self.trainer, is_active=True)
        self.api.patch(f'/api/exams/{exam.id}/', {'is_active': False}, format='json')
        info = self.ops(exam)['exam']
        self.assertFalse(info['is_live'])
        self.assertEqual(info['status'], 'ended')

    def test_a_dismissed_flag_is_not_flagged(self):
        exam = Exam.objects.create(title='E', created_by=self.trainer, is_active=True)
        q = Question.objects.create(exam=exam, title='Q', description='d')
        rows = {}
        for name, review in (('dismissed', 'dismissed'), ('pending', 'pending'), ('confirmed', 'confirmed')):
            s = User.objects.create_user(username=name, password='pw', role='student')
            sub = Submission.objects.create(student=s, exam=exam, question=q, code='x', language='python',
                                            attempt_number=1, status='passed')
            BehaviouralFlag.objects.create(submission=sub, risk_score=0.5, confidence='medium', review_status=review)
            rows[name] = s.id
        data = self.ops(exam)
        has_flag = {r['student_id']: r['has_flag'] for r in data['student_ops']}
        self.assertEqual(has_flag, {rows['dismissed']: False, rows['pending']: True, rows['confirmed']: True})
        self.assertEqual(data['flagged_students'], 2)

    def test_attempts_leave_out_refunded_errors(self):
        exam = Exam.objects.create(title='E', created_by=self.trainer, is_active=True)
        q = Question.objects.create(exam=exam, title='Q', description='d')
        s = User.objects.create_user(username='s', password='pw', role='student')
        for n, status in enumerate(('error', 'failed', 'passed'), start=1):
            Submission.objects.create(student=s, exam=exam, question=q, code='x', language='python',
                                      attempt_number=n, status=status)
        self.assertEqual(self.ops(exam)['student_ops'][0]['attempts'], 2)


class DisputeMatchedStudentTest(TestCase):
    """The dispute page links the matched student by their user id, not the submission id."""

    def test_matched_submission_carries_the_matched_students_id(self):
        from plagiarism.models import PlagiarismFlag
        from support.models import DisputeRequest
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        exam = Exam.objects.create(title='E', created_by=trainer, is_active=True)
        q = Question.objects.create(exam=exam, title='Q', description='d')
        a, b = (User.objects.create_user(username=n, password='pw', role='student') for n in ('a', 'b'))
        # pad submission ids so they can't coincide with the user ids
        for n in range(1, 4):
            Submission.objects.create(student=a, exam=exam, question=q, code='pad', language='python', attempt_number=n)
        s1, s2 = (Submission.objects.create(student=u, exam=exam, question=q, code='x', language='python',
                                            attempt_number=n) for u, n in ((a, 4), (b, 1)))
        flag = PlagiarismFlag.objects.create(submission_1=s1, submission_2=s2, similarity_score=0.95, flagged=True)
        dispute = DisputeRequest.objects.create(student=a, flag_type='similarity', flag_id=flag.id, student_note='mine')
        api = APIClient()
        api.force_authenticate(trainer)
        matched = api.get(f'/api/support/disputes/{dispute.id}/').data['matched_submission']
        self.assertEqual((matched['id'], matched['student_id']), (s2.id, b.id))
