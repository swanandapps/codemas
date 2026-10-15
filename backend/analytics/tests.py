"""Unit tests for analytics.metrics — the single source of truth for every rate."""
from django.test import SimpleTestCase, TestCase

from accounts.models import User
from exams.models import ExamEnrollment
from submissions.models import Submission

from analytics import metrics
from analytics.testing import EXPECTED, build_fixture


class PctTest(SimpleTestCase):

    def test_rounds_to_one_decimal(self):
        self.assertEqual(metrics.pct(1, 3), 33.3)
        self.assertEqual(metrics.pct(2, 3), 66.7)

    def test_zero_denominator_is_none(self):
        self.assertIsNone(metrics.pct(0, 0))

    def test_whole_numbers(self):
        self.assertEqual(metrics.pct(0, 4), 0.0)
        self.assertEqual(metrics.pct(4, 4), 100.0)


class RiskTest(SimpleTestCase):

    def test_risk_is_score_times_100_rounded(self):
        self.assertEqual(metrics.risk(0.734), 73)
        self.assertEqual(metrics.risk(0.735), 74)
        self.assertEqual(metrics.risk(1.0), 100)
        self.assertEqual(metrics.risk(0), 0)

    def test_none_is_none(self):
        self.assertIsNone(metrics.risk(None))


class MetricsFixtureTest(TestCase):

    def setUp(self):
        self.f = build_fixture()
        self.subs_a = Submission.objects.filter(exam=self.f.exam_a)
        self.subs_b = Submission.objects.filter(exam=self.f.exam_b)

    # ── population ───────────────────────────────────────────────────────
    def test_students_excludes_superuser_and_trainer(self):
        names = set(metrics.students().values_list('username', flat=True))
        self.assertNotIn('root', names)
        self.assertNotIn('trainer', names)
        self.assertIn('a1', names)

    def test_student_submissions_excludes_superuser(self):
        self.assertFalse(metrics.student_submissions(self.subs_a).filter(student=self.f.root).exists())

    # ── success rate (students who passed the exam) ─────────────────────
    def test_exam_success_is_students_who_passed_over_students_who_took(self):
        self.assertEqual(metrics.success(self.subs_a), {'passed': 3, 'taken': 5, 'accepted_rate': 60.0})
        self.assertEqual(metrics.success(self.subs_b), {'passed': 1, 'taken': 2, 'accepted_rate': 50.0})

    def test_success_zero_denominator_is_none(self):
        self.assertEqual(metrics.success(Submission.objects.none()), {'passed': 0, 'taken': 0, 'accepted_rate': None})

    def test_student_success_is_exams_passed_over_exams_taken(self):
        by = metrics.success_by(Submission.objects.all(), 'student_id')
        self.assertEqual(by[self.f.a1.id]['accepted_rate'], 100.0)
        self.assertEqual(by[self.f.a2.id]['accepted_rate'], 0.0)   # took it (a pending one counts), solved nothing
        self.assertEqual(by[self.f.a6.id]['accepted_rate'], 100.0)   # 1 of 2 questions is half: passed
        self.assertNotIn(self.f.root.id, by)
        self.assertNotIn(self.f.a4.id, by)

    def test_section_success_per_exam(self):
        by = metrics.success_by(Submission.objects.all(), 'student__cohort', 'exam_id')
        self.assertEqual(by[('Alpha', self.f.exam_a.id)]['accepted_rate'], 60.0)
        self.assertEqual(by[('Beta', self.f.exam_b.id)]['accepted_rate'], 50.0)

    def test_exam_results_count_every_question_of_the_exam(self):
        rows = {r['student_id']: r for r in metrics.exam_results(self.subs_a)}
        self.assertEqual({k: rows[self.f.a1.id][k] for k in ('solved', 'total', 'passed')}, {'solved': 2, 'total': 2, 'passed': True})
        self.assertEqual((rows[self.f.a3.id]['solved'], rows[self.f.a3.id]['passed']), (1, True))   # qa2 error never solves; 1 of 2 is half
        self.assertEqual((rows[self.f.a2.id]['solved'], rows[self.f.a2.id]['passed']), (0, False))
        self.assertNotIn(self.f.root.id, rows)

    def test_question_success_is_students_who_solved_over_students_who_attempted(self):
        by = metrics.question_success_by(self.subs_a)
        self.assertEqual(by[self.f.qa1.id], {'solved_students': 2, 'attempted_students': 4, 'accepted_rate': 50.0})
        # a2's pending and a3's error are not attempts
        self.assertEqual(by[self.f.qa2.id], {'solved_students': 2, 'attempted_students': 2, 'accepted_rate': 100.0})

    def test_question_success_by_exam(self):
        by = metrics.question_success_by(Submission.objects.all(), 'exam_id')
        self.assertEqual(by[(self.f.exam_b.id, self.f.qb2.id)]['accepted_rate'], 0.0)
        qid, _ = metrics.hardest_question({q: r for (e, q), r in by.items() if e == self.f.exam_a.id})
        self.assertEqual(qid, self.f.qa1.id)

    # ── flagged students ─────────────────────────────────────────────────
    def test_flagged_students_over_students_who_took(self):
        self.assertEqual(metrics.flagged_students(self.subs_a), {
            'flagged_students': 2, 'took': 5, 'flagged_students_rate': 40.0,
        })

    def test_flagged_students_ignores_superuser_flag(self):
        by = metrics.flagged_students_by(Submission.objects.all(), 'exam_id')
        self.assertEqual(by[self.f.exam_a.id]['flagged_students'], 2)

    def test_flagged_students_zero_denominator_is_none(self):
        self.assertEqual(metrics.flagged_students(Submission.objects.none()), {
            'flagged_students': 0, 'took': 0, 'flagged_students_rate': None,
        })

    # ── participation ────────────────────────────────────────────────────
    def test_participation(self):
        enr = ExamEnrollment.objects.filter(exam=self.f.exam_b)
        self.assertEqual(metrics.participation(self.subs_b, enr), {
            'took': 2, 'enrolled': 3, 'took_rate': 66.7,
        })

    def test_participation_excludes_superuser_enrolment(self):
        enr = ExamEnrollment.objects.filter(exam=self.f.exam_a)
        self.assertEqual(metrics.participation(self.subs_a, enr)['enrolled'], 5)

    def test_participation_zero_enrolled_is_none(self):
        self.assertIsNone(metrics.participation(self.subs_a, ExamEnrollment.objects.none())['took_rate'])

    # ── flags to review ──────────────────────────────────────────────────
    def test_flags_to_review_counts_pending_only(self):
        self.assertEqual(metrics.flags_to_review(self.subs_a), 1)
        self.assertEqual(metrics.flags_to_review(), 2)

    def test_flags_to_review_by_cohort(self):
        by = metrics.flags_to_review_by(Submission.objects.all(), 'student__cohort')
        self.assertEqual(by, {'Alpha': 1, 'Beta': 1})

    # ── exam summaries ───────────────────────────────────────────────────
    def test_exam_summary_matches_expected(self):
        self.assertEqual(metrics.exam_summary(self.f.exam_a.id), EXPECTED['A'])
        self.assertEqual(metrics.exam_summary(self.f.exam_b.id), EXPECTED['B'])

    def test_exam_summaries_batch_equals_single(self):
        batch = metrics.exam_summaries([self.f.exam_a.id, self.f.exam_b.id])
        self.assertEqual(batch[self.f.exam_a.id], metrics.exam_summary(self.f.exam_a.id))
        self.assertEqual(batch[self.f.exam_b.id], metrics.exam_summary(self.f.exam_b.id))

    def test_exam_summary_for_empty_exam_has_none_rates(self):
        from exams.models import Exam
        empty = Exam.objects.create(title='Empty', created_by=self.f.trainer)
        s = metrics.exam_summary(empty.id)
        self.assertEqual(s['took'], 0)
        self.assertIsNone(s['accepted_rate'])
        self.assertNotIn('solved_rate', s)
        self.assertIsNone(s['flagged_students_rate'])
        self.assertIsNone(s['took_rate'])

    def test_exam_summaries_is_query_efficient(self):
        with self.assertNumQueries(8):   # a constant: 4 grouped, plus 4 to leave voided questions out of solved
            metrics.exam_summaries([self.f.exam_a.id, self.f.exam_b.id])


class PassRuleTest(SimpleTestCase):
    """A student passed an exam when they solved at least half of its questions."""

    def test_at_least_half(self):
        self.assertTrue(metrics.passes(2, 3))
        self.assertTrue(metrics.passes(3, 4))
        self.assertTrue(metrics.passes(2, 2))
        self.assertTrue(metrics.passes(1, 2))
        self.assertTrue(metrics.passes(2, 4))
        self.assertFalse(metrics.passes(1, 3))
        self.assertFalse(metrics.passes(1, 4))
        self.assertFalse(metrics.passes(0, 2))

    def test_one_question_exam_solved_is_passed(self):
        self.assertTrue(metrics.passes(1, 1))
        self.assertFalse(metrics.passes(0, 1))

    def test_exam_without_questions_is_never_passed(self):
        self.assertFalse(metrics.passes(0, 0))


class SuccessRateTest(TestCase):
    """The pass rule against real submissions: a 3-question and a 1-question exam,
    two sections."""

    def setUp(self):
        from exams.models import Exam, Question
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.x, self.y = (User.objects.create_user(username=n, password='pw', role='student', cohort='S1') for n in 'xy')
        self.z, self.w = (User.objects.create_user(username=n, password='pw', role='student', cohort='S2') for n in 'zw')
        self.three = Exam.objects.create(title='Three', created_by=trainer)
        self.one = Exam.objects.create(title='One', created_by=trainer)
        self.q1, self.q2, self.q3 = (
            Question.objects.create(exam=self.three, title=t, description='d') for t in ('Q1', 'Q2', 'Q3')
        )
        self.only = Question.objects.create(exam=self.one, title='Only', description='d')

        attempt = {}

        def sub(stu, q, status):
            attempt[stu.id, q.id] = attempt.get((stu.id, q.id), 0) + 1
            Submission.objects.create(student=stu, exam=q.exam, question=q, code='x', language='python',
                                      attempt_number=attempt[stu.id, q.id], status=status)

        sub(self.x, self.q1, 'failed')
        sub(self.x, self.q1, 'passed')   # a retry that passes solves it
        sub(self.x, self.q2, 'passed')   # Q3 never attempted: 2 of 3 still passes
        sub(self.y, self.q1, 'passed')
        sub(self.y, self.q2, 'failed')   # 1 of 3
        sub(self.z, self.q1, 'error')    # refunded, never solved
        sub(self.z, self.q2, 'error')
        sub(self.z, self.q3, 'passed')   # 1 of 3
        sub(self.w, self.q1, 'pending')  # took it, nothing graded yet
        sub(self.x, self.only, 'passed')  # 1-question exam: solved it = passed
        sub(self.y, self.only, 'failed')

    def test_exam_level(self):
        by = metrics.success_by(Submission.objects.all(), 'exam_id')
        self.assertEqual(by[self.three.id], {'passed': 1, 'taken': 4, 'accepted_rate': 25.0})
        self.assertEqual(by[self.one.id], {'passed': 1, 'taken': 2, 'accepted_rate': 50.0})

    def test_student_level(self):
        by = metrics.success_by(Submission.objects.all(), 'student_id')
        self.assertEqual(by[self.x.id], {'passed': 2, 'taken': 2, 'accepted_rate': 100.0})
        self.assertEqual(by[self.y.id], {'passed': 0, 'taken': 2, 'accepted_rate': 0.0})
        self.assertEqual(by[self.z.id]['accepted_rate'], 0.0)
        self.assertEqual(by[self.w.id]['accepted_rate'], 0.0)

    def test_section_level(self):
        by = metrics.success_by(Submission.objects.filter(exam=self.three), 'student__cohort', 'exam_id')
        self.assertEqual(by[('S1', self.three.id)]['accepted_rate'], 50.0)
        self.assertEqual(by[('S2', self.three.id)]['accepted_rate'], 0.0)

    def test_question_level(self):
        by = metrics.question_success_by(Submission.objects.filter(exam=self.three))
        self.assertEqual(by[self.q1.id]['accepted_rate'], 100.0)   # x and y; z's error and w's pending don't count
        self.assertEqual(by[self.q2.id]['accepted_rate'], 50.0)
        self.assertEqual(by[self.q3.id]['accepted_rate'], 100.0)

    def test_summary_counts_passed_students(self):
        s = metrics.exam_summary(self.three.id)
        self.assertEqual((s['passed_students'], s['took'], s['accepted_rate']), (1, 4, 25.0))

    def test_grouped_queries_only(self):
        with self.assertNumQueries(6):   # a constant: 2 grouped, plus 4 to leave voided questions out of solved
            metrics.success_by(Submission.objects.all(), 'student_id')


class RankTieBreakTest(SimpleTestCase):
    """Rank by points; equal points are split by average solve time (faster first)."""

    def test_faster_student_ranks_higher_on_equal_points(self):
        scores = {1: 20, 2: 20, 3: 20, 4: 10}
        times = {1: 48, 2: 40, 3: 69}
        rank = {sid: metrics.competition_rank(scores, sid, times)['rank'] for sid in scores}
        self.assertEqual(rank, {2: 1, 1: 2, 3: 3, 4: 4})

    def test_same_points_and_time_share_a_rank_and_no_time_is_slowest(self):
        scores = {1: 20, 2: 20, 3: 20}
        times = {1: 40, 2: 40}
        rank = {sid: metrics.competition_rank(scores, sid, times)['rank'] for sid in scores}
        self.assertEqual(rank, {1: 1, 2: 1, 3: 3})

    def test_points_still_come_first(self):
        self.assertEqual(metrics.competition_rank({1: 30, 2: 20}, 2, {1: 999, 2: 1})['rank'], 2)
