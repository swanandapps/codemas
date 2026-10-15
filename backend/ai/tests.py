"""
Weekly recommendation and the per-exam question list behind My results.

Fixture:
    exam1 (started): easy E, medium M, hard H
    s1: E passed on attempt 1; M failed, then passed on attempt 2; H never attempted
    s2: enrolled, no submissions (no graded exam -> no recommendation)
    root: superuser with role student (never gets one)
"""
from datetime import date, timedelta
from unittest.mock import patch

from django.conf import settings
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, ExamEnrollment, Question
from submissions.models import Submission

from .llm import LLMUnavailable
from .models import WeeklyRecommendation
from .tasks import (
    generate_weekly_recommendation, weekly_recommendation_input, weekly_recommendation_students,
)

GOOD_REPLY = {
    'headline': 'You solve easy questions first time; medium ones take a second try.',
    'keep': {'text': 'Keep reading the examples first.', 'evidence': 'E: passed on attempt 1'},
    'work': {'text': 'Work on M before resubmitting.', 'evidence': 'M: passed on attempt 2'},
    'next': {'text': 'Try H this week.', 'evidence': 'H: not attempted'},
}
WEEK = date(2026, 10, 5)


class WeeklyFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        cls.s1 = User.objects.create_user(username='s1', password='pw', role='student', cohort='C')
        cls.s2 = User.objects.create_user(username='s2', password='pw', role='student', cohort='C')
        cls.root = User.objects.create_user(username='root', password='pw', role='student', cohort='C',
                                            is_superuser=True, is_staff=True)
        cls.exam = Exam.objects.create(title='Exam 1', created_by=trainer, duration_minutes=60,
                                       start_time=now - timedelta(days=2))
        cls.E = Question.objects.create(exam=cls.exam, title='E', description='d', difficulty='easy')
        cls.M = Question.objects.create(exam=cls.exam, title='M', description='d', difficulty='medium')
        cls.H = Question.objects.create(exam=cls.exam, title='H', description='d', difficulty='hard')
        for s in (cls.s1, cls.s2, cls.root):
            ExamEnrollment.objects.create(exam=cls.exam, student=s)

        def sub(stu, q, attempt, status):
            Submission.objects.create(student=stu, exam=cls.exam, question=q, code='x', language='python',
                                      attempt_number=attempt, status=status)

        sub(cls.s1, cls.E, 1, 'passed')
        sub(cls.s1, cls.M, 1, 'failed')
        sub(cls.s1, cls.M, 2, 'passed')
        sub(cls.root, cls.E, 1, 'passed')

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c


class ExamQuestionListTests(WeeklyFixture):
    def test_every_question_is_listed_with_its_outcome(self):
        res = self.client_for(self.s1).get('/api/leaderboard/me/exams/')
        self.assertEqual(res.status_code, 200)
        exam = res.data[0]
        rows = {q['title']: q for q in exam['questions']}
        self.assertEqual(list(rows), ['E', 'M', 'H'])
        self.assertEqual((rows['E']['status'], rows['E']['passed_on'], rows['E']['attempts']), ('passed', 1, 1))
        self.assertEqual((rows['M']['status'], rows['M']['passed_on'], rows['M']['attempts']), ('passed', 2, 2))
        self.assertEqual((rows['H']['status'], rows['H']['attempts']), ('not_attempted', 0))
        self.assertEqual(exam['points_available'], 60)
        self.assertEqual(exam['points'], 30)
        self.assertEqual((exam['passed'], exam['questions_solved']), (True, 2))  # 2 of 3 questions: at least half
        self.assertNotIn('solved_rate', exam)

    def test_submission_list_carries_test_counts(self):
        from exams.models import TestCase as Case
        from results.models import Result
        sub = Submission.objects.get(student=self.s1, question=self.M, attempt_number=1)
        for passed in (True, False, False):
            Result.objects.create(submission=sub, passed=passed,
                                  test_case=Case.objects.create(question=self.M, input_data='1', expected_output='1'))
        rows = {r['id']: r for r in self.client_for(self.s1).get('/api/submissions/').data['results']}
        self.assertEqual((rows[sub.id]['tests_passed'], rows[sub.id]['tests_total']), (1, 3))


class WeeklyRecommendationTests(WeeklyFixture):
    def test_input_sorts_questions_by_outcome(self):
        [exam] = weekly_recommendation_input(self.s1)
        self.assertEqual(exam['score'], '30 / 60 points')
        self.assertEqual(exam['passed_first_try'], ['E (easy)'])
        self.assertEqual(exam['passed_after_retries'], ['M (medium): passed on attempt 2'])
        self.assertEqual(exam['not_passed'], [])
        self.assertEqual(exam['not_attempted'], ['H (hard)'])
        self.assertEqual(exam['result'], 'passed: solved 2 of 3 questions (at least half passes)')

    def test_only_students_with_a_graded_attempt(self):
        self.assertEqual(list(weekly_recommendation_students()), [self.s1])

    @patch('ai.tasks.call_json', return_value=GOOD_REPLY)
    def test_stores_one_per_week(self, call):
        rec = generate_weekly_recommendation(self.s1.id, WEEK)
        self.assertEqual(rec.headline, GOOD_REPLY['headline'])
        self.assertEqual([c['kind'] for c in rec.cards], ['keep', 'work', 'next'])
        self.assertEqual(rec.cards[1]['evidence'], 'M: passed on attempt 2')
        generate_weekly_recommendation(self.s1.id, WEEK)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(WeeklyRecommendation.objects.count(), 1)

    @patch('ai.tasks.call_json', return_value=GOOD_REPLY)
    def test_unchanged_numbers_carry_forward_without_a_call(self, call):
        generate_weekly_recommendation(self.s1.id, WEEK)
        nxt = generate_weekly_recommendation(self.s1.id, WEEK + timedelta(days=7))
        self.assertEqual(call.call_count, 1)
        self.assertEqual(nxt.headline, GOOD_REPLY['headline'])

    def test_failed_week_keeps_last_good_one(self):
        with patch('ai.tasks.call_json', return_value=GOOD_REPLY):
            generate_weekly_recommendation(self.s1.id, WEEK)
        Submission.objects.create(student=self.s1, exam=self.exam, question=self.H, code='x',
                                  language='python', attempt_number=1, status='failed')
        with patch('ai.tasks.call_json', side_effect=LLMUnavailable('down')):
            self.assertIsNone(generate_weekly_recommendation(self.s1.id, WEEK + timedelta(days=7)))
        res = self.client_for(self.s1).get('/api/ai/recommendation/me/')
        self.assertEqual(res.data['headline'], GOOD_REPLY['headline'])
        self.assertEqual(str(res.data['next_update']), '2026-10-12')

    @patch('ai.tasks.call_json', return_value={'headline': 'x', 'keep': {'text': 'y'}})
    def test_malformed_reply_is_not_stored(self, _):
        self.assertIsNone(generate_weekly_recommendation(self.s1.id, WEEK))
        self.assertFalse(WeeklyRecommendation.objects.exists())

    def test_no_graded_exam_no_call(self):
        with patch('ai.tasks.call_json') as call:
            self.assertIsNone(generate_weekly_recommendation(self.s2.id, WEEK))
        call.assert_not_called()

    def test_endpoint_is_204_until_written_and_only_shows_your_own(self):
        self.assertEqual(self.client_for(self.s1).get('/api/ai/recommendation/me/').status_code, 204)
        with patch('ai.tasks.call_json', return_value=GOOD_REPLY):
            generate_weekly_recommendation(self.s1.id, WEEK)
        self.assertEqual(self.client_for(self.s1).get('/api/ai/recommendation/me/').status_code, 200)
        self.assertEqual(self.client_for(self.s2).get('/api/ai/recommendation/me/').status_code, 204)

    def test_beat_runs_monday_morning_ist(self):
        entry = settings.CELERY_BEAT_SCHEDULE['weekly-recommendations']
        self.assertEqual(entry['task'], 'ai.tasks.weekly_recommendations_task')
        self.assertEqual(entry['schedule'].day_of_week, {1})
        self.assertEqual((entry['schedule'].hour, entry['schedule'].minute), ({1}, {30}))


class BackfillAiFeedbackTests(WeeklyFixture):
    def test_queues_only_missing_reviews_and_hints_for_failed(self):
        from io import StringIO
        from django.core.management import call_command
        from .models import RubricScore
        done = Submission.objects.get(student=self.s1, question=self.E)
        RubricScore.objects.create(submission=done, correctness_score=2, correctness_note='n',
                                   code_quality_score=2, code_quality_note='n', approach_score=2,
                                   approach_note='n', edge_case_score=2, edge_case_note='n',
                                   overall_feedback='f')
        failed = Submission.objects.get(student=self.s1, question=self.M, attempt_number=1)
        with patch('ai.tasks.score_rubric.delay') as rubric, patch('ai.tasks.generate_hint.delay') as hint:
            out = StringIO()
            call_command('backfill_ai_feedback', stdout=out)
        graded = set(Submission.objects.values_list('id', flat=True))
        self.assertEqual({c.args[0] for c in rubric.call_args_list}, graded - {done.id})
        self.assertEqual([c.args[0] for c in hint.call_args_list], [failed.id])
        self.assertIn('Queued 3 rubric reviews and 1 hints', out.getvalue())


class ExamSummaryReadyTests(TestCase):
    """The exam summary describes final results: only once the exam ended or the student submitted it."""

    def setUp(self):
        from .models import ExamSummary
        self.ExamSummary = ExamSummary
        now = timezone.now()
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.s = User.objects.create_user(username='s', password='pw', role='student', cohort='C')
        self.exam = Exam.objects.create(title='Live', created_by=trainer, duration_minutes=60, is_active=True,
                                        start_time=now - timedelta(minutes=10), end_time=now + timedelta(hours=1))
        q = Question.objects.create(exam=self.exam, title='Q', description='d', difficulty='easy')
        self.enrollment = ExamEnrollment.objects.create(exam=self.exam, student=self.s)
        Submission.objects.create(student=self.s, exam=self.exam, question=q, code='x', language='python',
                                  attempt_number=1, status='failed')

    def get(self):
        return self.client_for(self.s).get(f'/api/ai/exam-summary/{self.exam.id}/').data

    def client_for(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def test_live_exam_not_submitted_gets_no_summary_and_stores_nothing(self):
        with patch('ai.tasks.call_json', return_value={'summary': 'Early.'}) as call:
            data = self.get()
        self.assertEqual(data['status'], 'not_ready')
        call.assert_not_called()
        self.assertFalse(self.ExamSummary.objects.exists())

    def test_written_once_the_student_submits_the_exam(self):
        self.enrollment.finished_at = timezone.now()
        self.enrollment.save()
        with patch('ai.tasks.call_json', return_value={'summary': 'Final.'}):
            self.assertEqual(self.get()['summary'], 'Final.')

    def test_written_once_the_exam_ended(self):
        Exam.objects.filter(pk=self.exam.pk).update(is_active=False, end_time=timezone.now() - timedelta(minutes=1))
        with patch('ai.tasks.call_json', return_value={'summary': 'Final.'}):
            self.assertEqual(self.get()['summary'], 'Final.')

    def test_a_summary_written_mid_exam_is_rewritten_once_results_are_final(self):
        self.ExamSummary.objects.create(student=self.s, exam=self.exam, summary='Early.')
        self.assertEqual(self.get()['status'], 'not_ready')
        self.enrollment.finished_at = timezone.now()
        self.enrollment.save()
        with patch('ai.tasks.call_json', return_value={'summary': 'Final.'}):
            self.assertEqual(self.get()['summary'], 'Final.')
        self.assertEqual(self.ExamSummary.objects.get().summary, 'Final.')


class GenerateExamDraftShapeTests(TestCase):
    """The model sometimes answers in the wrong shape; a draft must still come back with its questions."""

    Q = {'title': 'Is Palindrome', 'description': 'Check a string.', 'difficulty': 'easy',
         'test_cases': [{'input_data': 'abba', 'expected_output': 'true'}, {'input_data': 'ab', 'expected_output': 'false'}]}

    def draft(self, *replies):
        from ai.tasks import generate_exam_draft
        with patch('ai.tasks.call_json', side_effect=list(replies)) as call:
            return generate_exam_draft('Palindrome Checker', 'javascript', 1, 'easy'), call

    def test_one_question_at_the_top_level_becomes_the_question(self):
        flat = {**self.Q, 'title': 'Palindrome Checker', 'description': 'This exam tests ...'}
        d, call = self.draft(flat)
        self.assertEqual(call.call_count, 1)
        self.assertEqual(len(d['questions']), 1)
        self.assertEqual(len(d['questions'][0]['test_cases']), 2)
        self.assertEqual(d['questions'][0]['description'], 'This exam tests ...')

    def test_no_questions_asks_once_more(self):
        d, call = self.draft({'title': 'P', 'description': 'x', 'questions': []},
                             {'title': 'P', 'description': 'x', 'questions': [self.Q]})
        self.assertEqual(call.call_count, 2)
        self.assertEqual([q['title'] for q in d['questions']], ['Is Palindrome'])

    def test_still_empty_after_the_retry_returns_an_empty_draft(self):
        d, call = self.draft({'title': 'P', 'questions': []}, {'title': 'P', 'questions': []})
        self.assertEqual(call.call_count, 2)
        self.assertEqual(d['questions'], [])


from support.tests_appeals import AppealScenario   # noqa: E402  (shared appeal fixture)


class ExamSummaryIntegrityTests(AppealScenario, TestCase):
    """The exam summary reflects the plagiarism decision, and is rewritten whenever it changes."""

    def setUp(self):
        from .models import ExamSummary
        self.ExamSummary = ExamSummary
        self.make()

    def prompt_for(self, student):
        from .tasks import generate_exam_summary
        self.ExamSummary.objects.filter(student=student).delete()
        with patch('ai.tasks.call_json', return_value={'summary': 'Done.'}) as call:
            generate_exam_summary(student.id, self.exam.id)
        system, user = call.call_args.args[:2]
        return system, user

    def test_withheld_points_are_in_the_input_and_never_praised(self):
        system, user = self.prompt_for(self.a)
        self.assertIn('20 points withheld after a plagiarism review', user)
        self.assertIn('QM (attempt 1): passed, points withheld', user)
        self.assertIn('Never praise', system)
        self.assertIn('neutrally', system)

    def test_an_open_appeal_is_under_review(self):
        self.file(self.a)
        self.assertIn('appeal is under review', self.prompt_for(self.a)[1])

    def test_an_overturned_decision_restores_the_points(self):
        self.rule(self.file(self.a).data['id'], 'overturn')
        user = self.prompt_for(self.a)[1]
        self.assertIn('overturned', user)
        self.assertNotIn('points withheld', user)

    def test_a_clean_student_gets_no_integrity_line(self):
        self.assertIn('Integrity: no plagiarism decision', self.prompt_for(self.c)[1])

    # ── the result line: a voided question is not solved, so it can fail the exam ──

    def test_result_line_counts_only_counted_solves(self):
        self.assertIn('Result: not passed: solved 0 of 2 questions (at least half passes); '
                      '1 solved question not counted: plagiarism confirmed by the trainer.', self.prompt_for(self.b)[1])
        self.assertIn('Result: passed: solved 1 of 2 questions (at least half passes); '
                      '1 solved question not counted: plagiarism confirmed by the trainer.', self.prompt_for(self.a)[1])
        self.assertIn('Result: passed: solved 1 of 2 questions (at least half passes).', self.prompt_for(self.c)[1])

    def test_weekly_input_result_mentions_the_plagiarism(self):
        from .tasks import weekly_recommendation_input
        [exam] = weekly_recommendation_input(self.b)
        self.assertEqual(exam['result'], 'not passed: solved 0 of 2 questions (at least half passes); '
                                         '1 solved question not counted: plagiarism confirmed by the trainer')

    # ── invalidation: every decision path deletes the stored summary so it is rewritten ──

    def stored(self, *students):
        for s in students:
            self.ExamSummary.objects.create(student=s, exam=self.exam, summary='old')

    def left(self):
        return set(self.ExamSummary.objects.values_list('student__username', flat=True))

    def test_behaviour_review_forgets_that_students_summary(self):
        self.stored(self.a, self.c)
        self.api(self.trainer).patch(f'/api/plagiarism/behavioural/{self.a_flag.id}/review/',
                                     {'review_status': 'dismissed', 'review_note': 'ok'}, format='json')
        self.assertEqual(self.left(), {'clean'})

    def test_pair_review_forgets_both_students_summaries(self):
        self.stored(self.a, self.b, self.c)
        self.api(self.trainer).patch(f'/api/plagiarism/{self.pair.id}/review/',
                                     {'review_status': 'dismissed', 'review_note': 'ok'}, format='json')
        self.assertEqual(self.left(), {'clean'})

    def test_filing_and_each_ruling_forget_the_summary(self):
        self.stored(self.a, self.b, self.c)
        a_appeal, b_appeal = self.file(self.a).data['id'], self.file(self.b).data['id']
        self.assertEqual(self.left(), {'clean'})
        self.stored(self.a, self.b)
        self.rule(a_appeal, 'uphold')
        self.assertEqual(self.left(), {'clean', 'classmate'})
        self.rule(b_appeal, 'overturn')
        self.assertEqual(self.left(), {'clean'})
