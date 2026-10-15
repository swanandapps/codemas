from django.test import SimpleTestCase, TestCase
from django.utils import timezone
from datetime import timedelta
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, Question, ExamEnrollment
from submissions.models import Submission
from plagiarism.models import BehaviouralFlag

from dashboard.health import (
    HEALTH_RULES,
    band_for_accepted,
    compute_delta,
    classify_cohort,
    classify_exam,
    build_dashboard_health,
)


# ─── band_for_accepted ─────────────────────────────────────────────────────

class BandForAcceptedTest(SimpleTestCase):

    def test_none_is_no_submissions(self):
        self.assertEqual(band_for_accepted(None), 'no_submissions')

    def test_70_is_thriving(self):
        self.assertEqual(band_for_accepted(70), 'thriving')

    def test_above_70_is_thriving(self):
        self.assertEqual(band_for_accepted(85), 'thriving')

    def test_just_below_70_is_steady(self):
        self.assertEqual(band_for_accepted(69.9), 'steady')

    def test_40_is_steady(self):
        self.assertEqual(band_for_accepted(40), 'steady')

    def test_just_below_40_is_struggling(self):
        self.assertEqual(band_for_accepted(39.9), 'struggling')

    def test_zero_is_struggling(self):
        self.assertEqual(band_for_accepted(0), 'struggling')


# ─── compute_delta ─────────────────────────────────────────────────────────

class ComputeDeltaTest(SimpleTestCase):

    def test_single_exam_has_no_previous(self):
        avg, delta = compute_delta([60])
        self.assertIsNone(avg)
        self.assertIsNone(delta)

    def test_empty_series_has_no_previous(self):
        avg, delta = compute_delta([])
        self.assertIsNone(avg)
        self.assertIsNone(delta)

    def test_two_exams_uses_single_previous(self):
        avg, delta = compute_delta([50, 60])
        self.assertEqual(avg, 50)
        self.assertEqual(delta, 10)

    def test_four_exams_uses_three_previous(self):
        # previous = [50, 60, 70] avg 60, latest 66 -> delta 6
        avg, delta = compute_delta([50, 60, 70, 66])
        self.assertEqual(avg, 60)
        self.assertEqual(delta, 6)

    def test_more_than_four_exams_only_uses_last_three_before_latest(self):
        # previous three before latest(62) = [59, 66, 60] avg 61.7 -> delta 0.3
        avg, delta = compute_delta([59, 61, 59, 66, 60, 62])
        self.assertEqual(avg, 61.7)
        self.assertEqual(delta, 0.3)


# ─── classify_exam (exam-level rules) ───────────────────────────────────────

class ClassifyExamTest(SimpleTestCase):
    """Exam health uses the accepted rate and the flagged-students rate."""

    def test_on_track(self):
        self.assertEqual(classify_exam(accepted_rate=60, flagged_students_rate=5), 'on_track')

    def test_watch_on_low_accepted(self):
        self.assertEqual(classify_exam(accepted_rate=54.9, flagged_students_rate=0), 'watch')

    def test_accepted_55_is_not_watch(self):
        self.assertEqual(classify_exam(accepted_rate=55, flagged_students_rate=0), 'on_track')

    def test_watch_on_flagged_students_30(self):
        self.assertEqual(classify_exam(accepted_rate=90, flagged_students_rate=30), 'watch')

    def test_flagged_students_29_9_is_not_watch(self):
        self.assertEqual(classify_exam(accepted_rate=90, flagged_students_rate=29.9), 'on_track')

    def test_at_risk_on_low_accepted(self):
        self.assertEqual(classify_exam(accepted_rate=39.9, flagged_students_rate=0), 'at_risk')

    def test_accepted_40_is_not_at_risk(self):
        self.assertEqual(classify_exam(accepted_rate=40, flagged_students_rate=0), 'watch')

    def test_at_risk_on_flagged_students_50(self):
        self.assertEqual(classify_exam(accepted_rate=90, flagged_students_rate=50), 'at_risk')

    def test_flagged_students_49_9_is_not_at_risk(self):
        self.assertEqual(classify_exam(accepted_rate=90, flagged_students_rate=49.9), 'watch')

    def test_at_risk_wins_over_watch(self):
        self.assertEqual(classify_exam(accepted_rate=10, flagged_students_rate=50), 'at_risk')

    def test_no_data_is_on_track(self):
        # nobody graded yet / nobody took it: rates are None, no rule can fire
        self.assertEqual(classify_exam(accepted_rate=None, flagged_students_rate=None), 'on_track')


# ─── classify_cohort (cohort-level rules + reasons) ─────────────────────────

class ClassifyCohortTest(SimpleTestCase):
    """Defaults: latest=90 (healthy), delta=0, struggling_share=0, flagged_students_rate=0,
    participation=100 unless a test overrides the specific lever under test."""

    def base(self, **overrides):
        kwargs = dict(
            latest_accepted=90, delta=0, struggling_share_pct=0,
            flagged_students_rate=0, participation_pct=100,
        )
        kwargs.update(overrides)
        return classify_cohort(**kwargs)

    def test_on_track_when_all_healthy(self):
        state, reasons = self.base()
        self.assertEqual(state, 'on_track')
        self.assertEqual(reasons, [])

    # at_risk thresholds
    def test_at_risk_latest_accepted_below_40(self):
        state, reasons = self.base(latest_accepted=39.9)
        self.assertEqual(state, 'at_risk')
        self.assertTrue(any('39.9' in r for r in reasons))

    def test_latest_accepted_exactly_40_not_at_risk(self):
        state, _ = self.base(latest_accepted=40)
        self.assertNotEqual(state, 'at_risk')

    def test_at_risk_struggling_share_25(self):
        state, reasons = self.base(struggling_share_pct=25)
        self.assertEqual(state, 'at_risk')
        self.assertTrue(any('25' in r for r in reasons))

    def test_struggling_share_24_9_not_at_risk(self):
        state, _ = self.base(struggling_share_pct=24.9)
        self.assertNotEqual(state, 'at_risk')

    def test_at_risk_flagged_students_50(self):
        state, reasons = self.base(flagged_students_rate=50)
        self.assertEqual(state, 'at_risk')
        self.assertIn('50% of students who took the latest exam were flagged', reasons)

    def test_flagged_students_49_9_not_at_risk(self):
        state, _ = self.base(flagged_students_rate=49.9)
        self.assertEqual(state, 'watch')

    def test_at_risk_participation_below_60(self):
        state, reasons = self.base(participation_pct=59.9)
        self.assertEqual(state, 'at_risk')
        self.assertTrue(any('59.9' in r for r in reasons))

    def test_participation_exactly_60_not_at_risk(self):
        state, _ = self.base(participation_pct=60)
        self.assertNotEqual(state, 'at_risk')

    def test_participation_none_never_triggers_at_risk(self):
        state, _ = self.base(participation_pct=None, latest_accepted=10)
        # still at_risk because of latest_accepted, but not due to participation
        self.assertEqual(state, 'at_risk')

    # watch thresholds
    def test_watch_latest_accepted_below_55(self):
        state, reasons = self.base(latest_accepted=54.9)
        self.assertEqual(state, 'watch')
        self.assertTrue(any('54.9' in r for r in reasons))

    def test_latest_accepted_exactly_55_not_watch(self):
        state, _ = self.base(latest_accepted=55)
        self.assertEqual(state, 'on_track')

    def test_watch_delta_minus_8(self):
        state, reasons = self.base(delta=-8)
        self.assertEqual(state, 'watch')
        self.assertTrue(any('8' in r for r in reasons))

    def test_delta_minus_7_9_not_watch(self):
        state, _ = self.base(delta=-7.9)
        self.assertEqual(state, 'on_track')

    def test_delta_none_never_triggers_watch(self):
        state, _ = self.base(delta=None)
        self.assertEqual(state, 'on_track')

    def test_watch_struggling_share_20(self):
        state, reasons = self.base(struggling_share_pct=20)
        self.assertEqual(state, 'watch')
        self.assertTrue(any('20' in r for r in reasons))

    def test_struggling_share_19_9_not_watch(self):
        state, _ = self.base(struggling_share_pct=19.9)
        self.assertEqual(state, 'on_track')

    def test_watch_flagged_students_30(self):
        state, reasons = self.base(flagged_students_rate=30)
        self.assertEqual(state, 'watch')
        self.assertIn('30% of students who took the latest exam were flagged', reasons)

    def test_flagged_students_29_9_not_watch(self):
        state, _ = self.base(flagged_students_rate=29.9)
        self.assertEqual(state, 'on_track')

    def test_flagged_students_none_never_triggers(self):
        state, _ = self.base(flagged_students_rate=None)
        self.assertEqual(state, 'on_track')

    def test_latest_accepted_none_never_triggers(self):
        state, _ = self.base(latest_accepted=None)
        self.assertEqual(state, 'on_track')

    def test_watch_participation_below_85(self):
        state, reasons = self.base(participation_pct=84.9)
        self.assertEqual(state, 'watch')

    def test_participation_exactly_85_not_watch(self):
        state, _ = self.base(participation_pct=85)
        self.assertEqual(state, 'on_track')

    def test_at_risk_wins_over_watch(self):
        state, reasons = self.base(latest_accepted=10, struggling_share_pct=20)
        self.assertEqual(state, 'at_risk')

    def test_multiple_watch_reasons_all_listed(self):
        state, reasons = self.base(latest_accepted=50, flagged_students_rate=32)
        self.assertEqual(state, 'watch')
        self.assertEqual(len(reasons), 2)


# ─── build_dashboard_health (DB-backed, endpoint shape) ─────────────────────

class BuildDashboardHealthTest(TestCase):

    def setUp(self):
        self.api = APIClient()
        self.trainer = User.objects.create_user(
            username='trainer1', password='pw', role='trainer'
        )
        self.student_not_trainer = User.objects.create_user(
            username='stu_plain', password='pw', role='student', cohort='Batch-X'
        )

        now = timezone.now()

        # Two exams for Batch-X, ordered by start_time
        self.exam1 = Exam.objects.create(
            title='Exam One', created_by=self.trainer, duration_minutes=60,
            start_time=now - timedelta(days=14),
        )
        self.exam2 = Exam.objects.create(
            title='Exam Two', created_by=self.trainer, duration_minutes=60,
            start_time=now - timedelta(days=1),
        )
        self.q1 = Question.objects.create(exam=self.exam1, title='Q1', description='d')
        self.q2 = Question.objects.create(exam=self.exam2, title='Q2', description='d')

        self.s1 = User.objects.create_user(username='s1', password='pw', role='student', cohort='Batch-X')
        self.s2 = User.objects.create_user(username='s2', password='pw', role='student', cohort='Batch-X')
        self.unassigned = User.objects.create_user(username='s3', password='pw', role='student', cohort='')

        ExamEnrollment.objects.create(exam=self.exam2, student=self.s1)
        ExamEnrollment.objects.create(exam=self.exam2, student=self.s2)

        Submission.objects.create(
            student=self.s1, exam=self.exam1, question=self.q1, code='x', language='python',
            attempt_number=1, status='passed',
        )
        sub2 = Submission.objects.create(
            student=self.s1, exam=self.exam2, question=self.q2, code='x', language='python',
            attempt_number=1, status='failed',
        )
        Submission.objects.create(
            student=self.s2, exam=self.exam2, question=self.q2, code='x', language='python',
            attempt_number=1, status='passed',
        )
        BehaviouralFlag.objects.create(
            submission=sub2, risk_score=0.5, confidence='medium', review_status='pending',
        )

    def test_shape_has_expected_top_level_keys(self):
        result = build_dashboard_health()
        self.assertEqual(
            set(result.keys()),
            {'summary', 'cohorts', 'exams', 'students_needing_help', 'rules'},
        )

    def test_summary_counts_unassigned_separately(self):
        result = build_dashboard_health()
        self.assertEqual(result['summary']['unassigned_students'], 1)
        # trainer has no 'cohort'; s1, s2, and student_not_trainer are all in Batch-X
        self.assertEqual(result['summary']['students'], 3)
        self.assertEqual(result['summary']['cohorts'], 1)

    def test_cohort_present_with_latest_exam_two(self):
        result = build_dashboard_health()
        cohort = result['cohorts'][0]
        self.assertEqual(cohort['cohort'], 'Batch-X')
        self.assertEqual(cohort['latest']['exam_id'], self.exam2.id)
        self.assertEqual(cohort['took'] if 'took' in cohort else cohort['latest']['took'], 2)

    def test_exam_row_uses_flagged_students_rate(self):
        # exam2: s1 (flagged) and s2 took it -> 1 of 2 students flagged = 50%,
        # not 1 flag / 2 submissions by coincidence: add a second s2 submission
        Submission.objects.create(
            student=self.s2, exam=self.exam2, question=self.q2, code='y', language='python',
            attempt_number=2, status='passed',
        )
        result = build_dashboard_health()
        row = next(e for e in result['exams'] if e['exam_id'] == self.exam2.id)
        self.assertEqual(row['flagged_students'], 1)
        self.assertEqual(row['flagged_students_rate'], 50.0)
        self.assertEqual(row['accepted_rate'], 50.0)   # s2 passed, s1 did not: 1 of 2 students
        self.assertEqual(row['health'], 'at_risk')
        self.assertNotIn('flag_rate', row)

    def test_cohort_reason_names_students_who_took_the_exam(self):
        result = build_dashboard_health()
        cohort = result['cohorts'][0]
        self.assertEqual(cohort['latest']['flagged_students_rate'], 50.0)
        self.assertIn('50.0% of students who took the latest exam were flagged', cohort['reasons'])

    def test_pending_submissions_do_not_count_toward_accepted(self):
        Submission.objects.create(
            student=self.s2, exam=self.exam2, question=self.q2, code='z', language='python',
            attempt_number=2, status='pending',
        )
        result = build_dashboard_health()
        row = next(e for e in result['exams'] if e['exam_id'] == self.exam2.id)
        self.assertEqual(row['accepted_rate'], 50.0)

    def test_rules_echoed_back(self):
        result = build_dashboard_health()
        self.assertEqual(result['rules'], HEALTH_RULES)

    def test_endpoint_rejects_non_trainer(self):
        self.api.force_authenticate(user=self.student_not_trainer)
        res = self.api.get('/api/dashboard/health/')
        self.assertEqual(res.status_code, 403)

    def test_endpoint_allows_trainer(self):
        self.api.force_authenticate(user=self.trainer)
        res = self.api.get('/api/dashboard/health/')
        self.assertEqual(res.status_code, 200)
        self.assertIn('cohorts', res.data)
