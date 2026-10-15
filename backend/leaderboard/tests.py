"""
Student-facing score, rank and progress numbers (My results, Home, Leaderboard).

Fixture, one cohort "C":
    exam1 (started, enrolled): easy E, medium M, hard H   -> 60 points available
    exam2 (starts in 2 days, enrolled): easy E2           -> not available yet
    exam3 (started, NOT enrolled): hard H3                -> not available to them

    s1: E passed twice (counts once), M passed   -> 30 points
    s2: E passed, M passed                       -> 30 points (tied with s1)
    s3: E failed, E passed                       -> 10 points
    root: superuser with role student, solves everything -> excluded everywhere
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, ExamEnrollment, Question
from submissions.models import Submission


class StudentScoreFixture(TestCase):
    @classmethod
    def setUpTestData(cls):
        now = timezone.now()
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')

        def student(name, **extra):
            return User.objects.create_user(username=name, password='pw', role='student', cohort='C', **extra)

        cls.s1, cls.s2, cls.s3 = student('s1'), student('s2'), student('s3')
        cls.root = student('root', is_superuser=True, is_staff=True)

        def exam(title, start):
            return Exam.objects.create(title=title, created_by=trainer, duration_minutes=60,
                                       start_time=start, end_time=start + timedelta(hours=1))

        cls.exam1 = exam('Exam 1', now - timedelta(days=5))
        cls.exam2 = exam('Exam 2', now + timedelta(days=2))
        cls.exam3 = exam('Exam 3', now - timedelta(days=3))

        def q(ex, title, difficulty):
            return Question.objects.create(exam=ex, title=title, description='d', difficulty=difficulty)

        cls.E, cls.M, cls.H = q(cls.exam1, 'E', 'easy'), q(cls.exam1, 'M', 'medium'), q(cls.exam1, 'H', 'hard')
        q(cls.exam2, 'E2', 'easy')
        q(cls.exam3, 'H3', 'hard')

        for s in (cls.s1, cls.s2, cls.s3, cls.root):
            ExamEnrollment.objects.create(exam=cls.exam1, student=s)
            ExamEnrollment.objects.create(exam=cls.exam2, student=s)

        attempts = {}

        def sub(stu, question, status):
            key = (stu.id, question.id)
            attempts[key] = attempts.get(key, 0) + 1
            Submission.objects.create(student=stu, exam=question.exam, question=question, code='x',
                                      language='python', attempt_number=attempts[key], status=status,
                                      execution_time_ms=100)

        sub(cls.s1, cls.E, 'passed')
        sub(cls.s1, cls.E, 'passed')
        sub(cls.s1, cls.M, 'passed')
        sub(cls.s2, cls.E, 'passed')
        sub(cls.s2, cls.M, 'passed')
        sub(cls.s3, cls.E, 'failed')
        sub(cls.s3, cls.E, 'passed')
        for question in (cls.E, cls.M, cls.H):
            sub(cls.root, question, 'passed')

    def me(self, user, path='/api/leaderboard/me/'):
        api = APIClient()
        api.force_authenticate(user)
        return api.get(path).data


class MyStatsTest(StudentScoreFixture):
    def test_score_counts_each_solved_question_once(self):
        self.assertEqual(self.me(self.s1)['score'], 30)

    def test_score_has_a_denominator_of_points_available(self):
        # exam1 only: exam2 hasn't started and they aren't enrolled in exam3
        self.assertEqual(self.me(self.s1)['score_available'], 60)

    def test_score_available_counts_questions_sharing_a_difficulty(self):
        # A second easy question in exam1 must add another 10 points, not collapse into the first
        Question.objects.create(exam=self.exam1, title='E-two', description='d', difficulty='easy')
        self.assertEqual(self.me(self.s1)['score_available'], 70)
        self.assertEqual(self.me(self.s1)['difficulty_progress']['easy']['available'], 2)

    def test_score_never_exceeds_score_available(self):
        for s in (self.s1, self.s2, self.s3):
            data = self.me(s)
            self.assertLessEqual(data['score'], data['score_available'])

    def test_tied_students_share_a_rank(self):
        self.assertEqual(self.me(self.s1)['rank'], 1)
        self.assertEqual(self.me(self.s2)['rank'], 1)
        self.assertEqual(self.me(self.s3)['rank'], 3)

    def test_ahead_of_uses_the_same_ranking(self):
        self.assertEqual(self.me(self.s1)['ahead_of'], 1)   # only s3 scored lower
        self.assertEqual(self.me(self.s3)['ahead_of'], 0)

    def test_cohort_size_excludes_superusers(self):
        self.assertEqual(self.me(self.s1)['cohort_size'], 3)

    def test_overall_rank_spans_every_cohort(self):
        # A student in another cohort solves E and H (40 points): first overall, not in cohort C
        other = User.objects.create_user(username='o1', password='pw', role='student', cohort='D')
        for question in (self.E, self.H):
            Submission.objects.create(student=other, exam=self.exam1, question=question, code='x',
                                      language='python', attempt_number=1, status='passed')
        mine = self.me(self.s1)
        self.assertEqual((mine['rank'], mine['cohort_size']), (1, 3))
        self.assertEqual((mine['overall_rank'], mine['overall_size']), (2, 4))
        board = APIClient()
        board.force_authenticate(self.s1)
        entry = next(e for e in board.get('/api/leaderboard/').data['leaderboard'] if e['student_id'] == self.s1.id)
        self.assertEqual(entry['rank'], mine['overall_rank'])  # matches the leaderboard's All view

    def test_difficulty_progress_has_solved_available_and_points(self):
        progress = self.me(self.s1)['difficulty_progress']
        self.assertEqual(progress['easy'], {'solved': 1, 'available': 1, 'points': 10, 'withheld': 0})
        self.assertEqual(progress['medium'], {'solved': 1, 'available': 1, 'points': 20, 'withheld': 0})
        self.assertEqual(progress['hard'], {'solved': 0, 'available': 1, 'points': 0, 'withheld': 0})

    def test_speed_metrics_are_gone(self):
        data = self.me(self.s1)
        self.assertNotIn('beats_pct', data)
        self.assertNotIn('avg_execution_time', data)


class LeaderboardTest(StudentScoreFixture):
    def board(self):
        return {row['username']: row for row in self.me(self.s1, '/api/leaderboard/')['leaderboard']}

    def test_scores_match_my_stats(self):
        board = self.board()
        for s in (self.s1, self.s2, self.s3):
            self.assertEqual(board[s.username]['score'], self.me(s)['score'])

    def test_no_speed_column_and_no_superuser(self):
        board = self.board()
        self.assertNotIn('root', board)
        for row in board.values():
            self.assertNotIn('avg_execution_time', row)


class MyExamStatsTest(StudentScoreFixture):
    def first_exam(self, user):
        return next(e for e in self.me(user, '/api/leaderboard/me/exams/') if e['exam_id'] == self.exam1.id)

    def test_points_count_each_solved_question_once(self):
        self.assertEqual(self.first_exam(self.s1)['points'], 30)

    def test_exam_rank_is_tie_aware(self):
        self.assertEqual(self.first_exam(self.s1)['rank'], 1)
        self.assertEqual(self.first_exam(self.s2)['rank'], 1)
        self.assertEqual(self.first_exam(self.s3)['rank'], 3)

    def test_attempts_leave_out_refunded_errors(self):
        Submission.objects.create(student=self.s2, exam=self.exam1, question=self.H, code='x', language='python',
                                  attempt_number=1, status='error')
        exam = self.first_exam(self.s2)
        self.assertEqual(exam['attempts'], 2)
        h = next(q for q in exam['questions'] if q['question_id'] == self.H.id)
        self.assertEqual((h['attempts'], h['status']), (0, 'not_attempted'))

    def test_summary_ready_once_the_exam_ended_or_the_student_submitted_it(self):
        self.assertTrue(self.first_exam(self.s1)['summary_ready'])   # exam1 ended
        live = Exam.objects.create(title='Live', created_by=self.exam1.created_by, is_active=True,
                                   start_time=timezone.now() - timedelta(minutes=5))
        q = Question.objects.create(exam=live, title='L', description='d', difficulty='easy')
        enrollment = ExamEnrollment.objects.create(exam=live, student=self.s1)
        Submission.objects.create(student=self.s1, exam=live, question=q, code='x', language='python',
                                  attempt_number=1, status='failed')

        def live_row():
            return next(e for e in self.me(self.s1, '/api/leaderboard/me/exams/') if e['exam_id'] == live.id)
        self.assertFalse(live_row()['summary_ready'])
        enrollment.finished_at = timezone.now()
        enrollment.save()
        self.assertTrue(live_row()['summary_ready'])


class ExamRankPopulationTest(TestCase):
    """A per-exam rank counts only the students who took that exam, and a student with no points
    on it (nothing solved, or everything withheld) is "Not ranked": rank None. The exam report
    uses the same rule."""

    def setUp(self):
        from plagiarism.models import BehaviouralFlag
        now = timezone.now()
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.exam = Exam.objects.create(title='R', created_by=self.trainer, start_time=now - timedelta(days=1),
                                        end_time=now - timedelta(hours=20))
        easy = Question.objects.create(exam=self.exam, title='E', description='d', difficulty='easy')
        medium = Question.objects.create(exam=self.exam, title='M', description='d', difficulty='medium')
        self.u = {n: User.objects.create_user(username=n, password='pw', role='student', cohort='A')
                  for n in ('top', 'second', 'zero', 'withheld', 'absent')}
        User.objects.create_user(username='never_enrolled', password='pw', role='student', cohort='A')
        for n in ('top', 'second', 'zero', 'withheld', 'absent'):
            ExamEnrollment.objects.create(exam=self.exam, student=self.u[n])

        def sub(n, q, status='passed'):
            return Submission.objects.create(student=self.u[n], exam=self.exam, question=q, code='x',
                                             language='python', attempt_number=1, status=status,
                                             time_to_complete_seconds=60)
        sub('top', medium)
        sub('second', easy)
        sub('zero', easy, 'failed')
        BehaviouralFlag.objects.create(submission=sub('withheld', easy), risk_score=0.8, confidence='high',
                                       review_status='confirmed')

    def mine(self, name):
        api = APIClient()
        api.force_authenticate(self.u[name])
        return next(e for e in api.get('/api/leaderboard/me/exams/').data if e['exam_id'] == self.exam.id)

    def test_my_results_ranks_among_those_who_took_it(self):
        self.assertEqual((self.mine('top')['rank'], self.mine('top')['cohort_size']), (1, 4))
        self.assertEqual((self.mine('second')['rank'], self.mine('second')['cohort_size']), (2, 4))

    def test_no_points_is_not_ranked(self):
        for n in ('zero', 'withheld'):
            self.assertIsNone(self.mine(n)['rank'], n)
            self.assertEqual(self.mine(n)['cohort_size'], 4)

    def test_report_does_not_rank_zero_points(self):
        api = APIClient()
        api.force_authenticate(self.trainer)
        rows = {r['username']: r for r in api.get(f'/api/dashboard/exams/{self.exam.id}/').data['students']}
        self.assertEqual({n: rows[n]['rank'] for n in rows},
                         {'top': 1, 'second': 2, 'zero': None, 'withheld': None, 'absent': None})
        self.assertEqual([r['username'] for r in api.get(f'/api/dashboard/exams/{self.exam.id}/').data['students']][:2],
                         ['top', 'second'])
