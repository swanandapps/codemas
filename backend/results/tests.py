import json
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, ExamEnrollment, Question, TestCase as QTest
from results.models import Result
from submissions.models import Submission

HIDDEN_IN = 'SECRET-INPUT-7f3a'
HIDDEN_OUT = 'SECRET-EXPECTED-9c1d'
VISIBLE_IN = 'visible-input-42'
VISIBLE_OUT = 'visible-expected-43'


class HiddenTestCaseLeakTest(TestCase):
    """A hidden test's input and expected output never reach a student, from any endpoint
    that carries test data. Trainers still see everything; visible tests show fully."""

    def setUp(self):
        self.trainer = User.objects.create_user(username='ht', password='pw', role='trainer')
        self.student = User.objects.create_user(username='hs', password='pw', role='student', cohort='C')
        now = timezone.now()
        self.exam = Exam.objects.create(title='E', created_by=self.trainer, is_active=True,
                                        start_time=now - timedelta(hours=1), end_time=now + timedelta(hours=1))
        ExamEnrollment.objects.create(exam=self.exam, student=self.student)
        self.q = Question.objects.create(exam=self.exam, title='Q', description='d')
        self.hidden = QTest.objects.create(question=self.q, input_data=HIDDEN_IN, expected_output=HIDDEN_OUT,
                                           is_hidden=True)
        self.visible = QTest.objects.create(question=self.q, input_data=VISIBLE_IN, expected_output=VISIBLE_OUT,
                                            is_hidden=False)
        self.sub = Submission.objects.create(student=self.student, exam=self.exam, question=self.q,
                                             code='print(1)', language='python', status='failed',
                                             attempt_number=1)
        Result.objects.create(submission=self.sub, test_case=self.hidden, passed=False, actual_output='student-out')
        Result.objects.create(submission=self.sub, test_case=self.visible, passed=True, actual_output=VISIBLE_OUT)
        self.api = APIClient()

    def get(self, user, url):
        self.api.force_authenticate(user)
        r = self.api.get(url)
        self.assertEqual(r.status_code, 200, url)
        return r, json.dumps(r.json())

    def assert_no_hidden(self, raw):
        self.assertNotIn(HIDDEN_IN, raw)
        self.assertNotIn(HIDDEN_OUT, raw)

    def assert_visible(self, raw):
        self.assertIn(VISIBLE_IN, raw)
        self.assertIn(VISIBLE_OUT, raw)

    def test_student_exam_detail_has_no_hidden_data_but_keeps_the_count(self):
        r, raw = self.get(self.student, f'/api/exams/{self.exam.id}/')
        self.assert_no_hidden(raw)
        self.assert_visible(raw)
        tcs = r.json()['questions'][0]['test_cases']
        self.assertEqual(len(tcs), 2)  # count still right for "2 test cases"
        self.assertIn({'id': self.hidden.id, 'is_hidden': True}, tcs)

    def test_student_exam_list_and_question_list_have_no_hidden_data(self):
        _, raw = self.get(self.student, '/api/exams/')
        self.assert_no_hidden(raw)
        self.assert_visible(raw)
        _, raw = self.get(self.student, f'/api/exams/{self.exam.id}/questions/')
        self.assert_no_hidden(raw)
        self.assert_visible(raw)

    def test_student_results_have_no_hidden_data(self):
        r, raw = self.get(self.student, f'/api/results/{self.sub.id}/')
        self.assert_no_hidden(raw)
        self.assert_visible(raw)
        hidden_row = next(x for x in r.json() if x['is_hidden'])
        self.assertIsNone(hidden_row['test_case_input'])
        self.assertIsNone(hidden_row['test_case_expected'])
        self.assertEqual(hidden_row['actual_output'], 'student-out')  # own output still shown
        self.assertFalse(hidden_row['passed'])

    def test_student_submission_detail_and_list_have_no_hidden_data(self):
        _, raw = self.get(self.student, f'/api/submissions/{self.sub.id}/')
        self.assert_no_hidden(raw)
        _, raw = self.get(self.student, '/api/submissions/')
        self.assert_no_hidden(raw)

    def test_trainer_still_sees_hidden_data_everywhere(self):
        for url in (f'/api/exams/{self.exam.id}/', '/api/exams/', f'/api/exams/{self.exam.id}/questions/',
                    f'/api/results/{self.sub.id}/'):
            _, raw = self.get(self.trainer, url)
            self.assertIn(HIDDEN_IN, raw, url)
            self.assertIn(HIDDEN_OUT, raw, url)
            self.assert_visible(raw)
