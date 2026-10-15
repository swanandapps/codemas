"""
Cross-endpoint consistency: for the same exam (or student), every endpoint
that reports a canonical metric must return the identical value.

Fixture and hand-computed expectations live in analytics/testing.py.
"""
from django.test import TestCase
from rest_framework.test import APIClient

from analytics.testing import EXPECTED, build_fixture


EXAM_FIELDS = [
    'took', 'enrolled', 'took_rate',
    'passed_students', 'accepted_rate',
    'flagged_students', 'flagged_students_rate',
]


class ExamMetricsConsistencyTest(TestCase):

    def setUp(self):
        self.f = build_fixture()
        self.api = APIClient()
        self.api.force_authenticate(user=self.f.trainer)

    def _get(self, url):
        res = self.api.get(url)
        self.assertEqual(res.status_code, 200, url)
        return res.data

    def _sources(self, exam, cohort):
        """Every place an exam-level canonical metric is reported, keyed by a readable name."""
        history = next(r for r in self._get('/api/dashboard/exams/') if r['exam_id'] == exam.id)
        detail = self._get(f'/api/dashboard/exams/{exam.id}/')
        ops = self._get(f'/api/support/exam/{exam.id}/ops/')
        cohort_row = next(r for r in self._get('/api/plagiarism/cohorts/') if r['exam_id'] == exam.id)
        cohort_detail = self._get(f'/api/plagiarism/cohorts/{exam.id}/')['stats']
        health = self._get('/api/dashboard/health/')
        health_exam = next(r for r in health['exams'] if r['exam_id'] == exam.id)
        health_cohort = next(c for c in health['cohorts'] if c['cohort'] == cohort)
        self.assertEqual(health_cohort['latest']['exam_id'], exam.id)
        return {
            'exam history row': history,
            'exam detail': detail,
            'exam ops': ops,
            'investigations list row': cohort_row,
            'investigation detail': cohort_detail,
            'overview exam row': health_exam,
            'overview cohort latest': health_cohort['latest'],
        }

    def _assert_consistent(self, exam, cohort, key):
        sources = self._sources(exam, cohort)
        for field in EXAM_FIELDS:
            for name, payload in sources.items():
                with self.subTest(exam=key, field=field, source=name):
                    self.assertIn(field, payload)
                    self.assertEqual(payload[field], EXPECTED[key][field])

    def test_no_second_percentage_next_to_success_rate(self):
        for name, payload in self._sources(self.f.exam_a, 'Alpha').items():
            with self.subTest(source=name):
                self.assertNotIn('solved_rate', payload)

    def test_section_card_is_the_sections_students_who_passed(self):
        alpha = next(c for c in self._get('/api/dashboard/health/')['cohorts'] if c['cohort'] == 'Alpha')
        self.assertEqual(alpha['series'][-1]['accepted_rate'], 60.0)
        self.assertEqual(alpha['latest']['accepted_rate'], 60.0)

    def test_question_success_identical_everywhere(self):
        history = next(r for r in self._get('/api/dashboard/exams/') if r['exam_id'] == self.f.exam_a.id)
        detail = self._get(f'/api/dashboard/exams/{self.f.exam_a.id}/')
        overview = next(r for r in self._get('/api/dashboard/health/')['exams'] if r['exam_id'] == self.f.exam_a.id)
        for name, payload in {'exam history row': history, 'exam detail': detail, 'overview exam row': overview}.items():
            with self.subTest(source=name):
                self.assertEqual((payload['hardest_question'], payload['hardest_accepted_rate']), ('QA1', 50.0))
        for payload in (history, detail):
            rows = {q['title']: q for q in payload['questions']}
            self.assertEqual(
                (rows['QA1']['solved_students'], rows['QA1']['attempted_students'], rows['QA1']['accepted_rate']),
                (2, 4, 50.0),
            )
            self.assertEqual(rows['QA2']['accepted_rate'], 100.0)

    def test_exam_a_identical_everywhere(self):
        self._assert_consistent(self.f.exam_a, 'Alpha', 'A')

    def test_exam_b_identical_everywhere(self):
        self._assert_consistent(self.f.exam_b, 'Beta', 'B')

    def test_dismissed_flag_leaves_flagged_everywhere(self):
        from plagiarism.models import BehaviouralFlag
        BehaviouralFlag.objects.filter(submission__student=self.f.a3).update(review_status='dismissed')
        for name, payload in self._sources(self.f.exam_a, 'Alpha').items():
            with self.subTest(source=name):
                self.assertEqual((payload['flagged_students'], payload['flagged_students_rate']), (1, 20.0))
        ops = {r['student_id']: r for r in self._get(f'/api/support/exam/{self.f.exam_a.id}/ops/')['student_ops']}
        self.assertFalse(ops[self.f.a3.id]['has_flag'])
        self.assertTrue(ops[self.f.a5.id]['has_flag'])
        students = {s['student_id']: s for s in self._get('/api/dashboard/students/')}
        self.assertIsNone(students[self.f.a3.id]['max_confidence'])
        report = {s['student_id']: s for s in self._get(f'/api/dashboard/exams/{self.f.exam_a.id}/')['students']}
        self.assertEqual(report[self.f.a3.id]['behavioural_flags'], 0)

    def test_dismissed_flag_leaves_students_needing_help_flag_count(self):
        from plagiarism.models import BehaviouralFlag
        help_rows = lambda: {r['student_id']: r for r in self._get('/api/dashboard/health/')['students_needing_help']}
        self.assertEqual(help_rows()[self.f.a5.id]['flags'], 1)
        BehaviouralFlag.objects.filter(submission__student=self.f.a5).update(review_status='dismissed')
        self.assertEqual(help_rows()[self.f.a5.id]['flags'], 0)

    def test_flags_to_review_consistent(self):
        health = self._get('/api/dashboard/health/')
        per_cohort = {c['cohort']: c['flags_to_review'] for c in health['cohorts']}
        self.assertEqual(per_cohort, {'Alpha': 1, 'Beta': 1})
        mon = self._get('/api/plagiarism/monitoring/')
        self.assertEqual(mon['summary']['behavioural']['flags_to_review'], 2)
        detail = self._get(f'/api/dashboard/exams/{self.f.exam_a.id}/')
        self.assertEqual(detail['flags_to_review'], 1)

    def test_health_rules_use_flagged_students_thresholds(self):
        rules = self._get('/api/dashboard/health/')['rules']
        self.assertEqual(rules['watch']['flagged_students_pct'], 30)
        self.assertEqual(rules['at_risk']['flagged_students_pct'], 50)
        self.assertNotIn('flag_rate_pct', rules['watch'])

    def test_superuser_never_counted(self):
        detail = self._get(f'/api/dashboard/exams/{self.f.exam_a.id}/')
        self.assertNotIn(self.f.root.id, [s['student_id'] for s in detail['students']])
        ops = self._get(f'/api/support/exam/{self.f.exam_a.id}/ops/')
        self.assertNotIn(self.f.root.id, [s['student_id'] for s in ops['student_ops']])
        students = self._get('/api/dashboard/students/')
        self.assertNotIn(self.f.root.id, [s['student_id'] for s in students])
        board = self._get('/api/leaderboard/')['leaderboard']
        self.assertNotIn(self.f.root.id, [s['student_id'] for s in board])


class StudentMetricsConsistencyTest(TestCase):
    """A student's success rate (exams passed ÷ exams taken) is the same on every page that shows it."""

    def setUp(self):
        self.f = build_fixture()
        self.api = APIClient()

    def _overall_success_sources(self, student):
        self.api.force_authenticate(user=self.f.trainer)
        students = {s['student_id']: s for s in self.api.get('/api/dashboard/students/').data}
        detail = self.api.get(f'/api/dashboard/students/{student.id}/').data['student']
        board = {s['student_id']: s for s in self.api.get('/api/leaderboard/').data['leaderboard']}
        self.api.force_authenticate(user=student)
        me = self.api.get('/api/leaderboard/me/').data
        return {
            'students list': students[student.id]['accepted_rate'],
            'student detail': detail['accepted_rate'],
            'leaderboard': board[student.id]['accepted_rate'],
            'my stats': me['accepted_rate'],
        }

    def _needing_help(self):
        self.api.force_authenticate(user=self.f.trainer)
        return {r['student_id']: r for r in self.api.get('/api/dashboard/health/').data['students_needing_help']}

    def test_a1_overall_success_identical(self):
        for name, value in self._overall_success_sources(self.f.a1).items():
            with self.subTest(source=name):
                self.assertEqual(value, 100.0)
        self.assertNotIn(self.f.a1.id, self._needing_help())

    def test_a2_overall_success_identical_and_in_needing_help(self):
        for name, value in self._overall_success_sources(self.f.a2).items():
            with self.subTest(source=name):
                self.assertEqual(value, 0.0)
        self.assertEqual(self._needing_help()[self.f.a2.id]['accepted_rate'], 0.0)

    def test_a6_one_of_two_solved_is_a_pass_everywhere(self):
        for name, value in self._overall_success_sources(self.f.a6).items():
            with self.subTest(source=name):
                self.assertEqual(value, 100.0)
        self.assertNotIn(self.f.a6.id, self._needing_help())

    def test_my_stats_counts_exams(self):
        self.api.force_authenticate(user=self.f.a1)
        me = self.api.get('/api/leaderboard/me/').data
        self.assertEqual((me['exams_passed'], me['exams_taken']), (1, 1))

    def _per_exam(self, student, exam):
        self.api.force_authenticate(user=self.f.trainer)
        report = next(s for s in self.api.get(f'/api/dashboard/exams/{exam.id}/').data['students'] if s['student_id'] == student.id)
        trend = next(p for p in self.api.get(f'/api/dashboard/students/{student.id}/').data['performance_trend'] if p['exam'] == exam.title)
        self.api.force_authenticate(user=student)
        mine = next(e for e in self.api.get('/api/leaderboard/me/exams/').data if e['exam_id'] == exam.id)
        return report, trend, mine

    def test_per_exam_pass_identical_on_report_trend_and_my_results(self):
        report, trend, mine = self._per_exam(self.f.a1, self.f.exam_a)
        self.assertEqual((report['passed'], report['questions_solved'], report['total_questions']), (True, 2, 2))
        self.assertEqual((trend['status'], trend['questions_solved'], trend['questions_total']), ('passed', 2, 2))
        self.assertEqual((mine['passed'], mine['questions_solved'], mine['questions_total']), (True, 2, 2))
        for payload in (report, trend, mine):
            self.assertNotIn('solved_rate', payload)

    def test_per_exam_half_solved_is_passed_everywhere(self):
        report, trend, mine = self._per_exam(self.f.a6, self.f.exam_a)
        self.assertEqual((report['passed'], report['questions_solved']), (True, 1))
        self.assertEqual((trend['status'], trend['questions_solved']), ('passed', 1))
        self.assertEqual((mine['passed'], mine['questions_solved']), (True, 1))

    def test_enrolled_student_who_never_submitted_has_no_result(self):
        self.api.force_authenticate(user=self.f.trainer)
        report = {s['student_id']: s for s in self.api.get(f'/api/dashboard/exams/{self.f.exam_a.id}/').data['students']}
        self.assertIsNone(report[self.f.a4.id]['passed'])
