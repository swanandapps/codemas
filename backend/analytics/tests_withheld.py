"""
Confirmed plagiarism costs the student their points (and so their rank); a pending
flag only marks the student "Under review" on trainer pages.

Voided (student, question): the student's points for the question are withheld when, on
that question, they have a CONFIRMED behavioural flag on any of their submissions, or a
CONFIRMED similarity pair on one of their submissions AND a behavioural flag (not
dismissed) of their own. A confirmed pair alone never voids: it protects the classmate
whose code merely matched.
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, ExamEnrollment, Question
from plagiarism.models import BehaviouralFlag, PlagiarismFlag
from submissions.models import Submission

from analytics import metrics


class _Scenario:
    """One ended exam in section Gamma: qe (easy, 10 points) and qm (medium, 20 points)."""

    def make(self):
        now = timezone.now()
        self.trainer = User.objects.create_user(username='trainer_w', password='pw', role='trainer')
        self.exam = Exam.objects.create(
            title='Exam W', created_by=self.trainer, duration_minutes=60,
            start_time=now - timedelta(days=2), end_time=now - timedelta(days=2) + timedelta(hours=1),
        )
        self.qe = Question.objects.create(exam=self.exam, title='QE', description='d', difficulty='easy')
        self.qm = Question.objects.create(exam=self.exam, title='QM', description='d', difficulty='medium')
        self._attempt = {}

    def student(self, name, cohort='Gamma'):
        s = User.objects.create_user(username=name, password='pw', role='student', cohort=cohort)
        ExamEnrollment.objects.create(exam=self.exam, student=s)
        return s

    def sub(self, stu, q, status='passed', seconds=60):
        key = (stu.id, q.id)
        self._attempt[key] = self._attempt.get(key, 0) + 1
        return Submission.objects.create(
            student=stu, exam=self.exam, question=q, code='x', language='python',
            attempt_number=self._attempt[key], status=status, time_to_complete_seconds=seconds,
        )

    @staticmethod
    def behaviour(sub, review_status):
        return BehaviouralFlag.objects.create(submission=sub, risk_score=0.6, confidence='medium', review_status=review_status)

    @staticmethod
    def pair(sub_1, sub_2, review_status, flagged=True):
        return PlagiarismFlag.objects.create(
            submission_1=sub_1, submission_2=sub_2, similarity_score=0.95,
            flagged=flagged, review_status=review_status,
        )


class VoidedPairsTest(_Scenario, TestCase):

    def setUp(self):
        self.make()
        self.s1, self.s2 = self.student('w1'), self.student('w2')

    def _voided(self):
        return metrics.voided_pairs(Submission.objects.filter(exam=self.exam))

    def test_confirmed_behavioural_flag_voids_the_question(self):
        self.behaviour(self.sub(self.s1, self.qe), 'confirmed')
        self.assertEqual(self._voided(), {(self.s1.id, self.qe.id)})

    def test_confirmed_behavioural_flag_on_a_failed_attempt_still_voids(self):
        self.behaviour(self.sub(self.s1, self.qe, 'failed'), 'confirmed')
        self.sub(self.s1, self.qe, 'passed')
        self.assertEqual(self._voided(), {(self.s1.id, self.qe.id)})

    def test_confirmed_similarity_with_own_behavioural_flag_voids(self):
        mine = self.sub(self.s1, self.qe)
        self.behaviour(mine, 'pending')
        self.pair(mine, self.sub(self.s2, self.qe), 'confirmed')
        self.assertEqual(self._voided(), {(self.s1.id, self.qe.id)})

    def test_confirmed_similarity_only_does_not_void(self):
        self.pair(self.sub(self.s1, self.qe), self.sub(self.s2, self.qe), 'confirmed')
        self.assertEqual(self._voided(), set())

    def test_dismissed_flags_do_not_void(self):
        mine = self.sub(self.s1, self.qe)
        self.behaviour(mine, 'dismissed')
        self.pair(mine, self.sub(self.s2, self.qe), 'confirmed')
        self.behaviour(self.sub(self.s2, self.qm), 'dismissed')
        self.assertEqual(self._voided(), set())

    def test_pending_flags_do_not_void(self):
        mine = self.sub(self.s1, self.qe)
        self.behaviour(mine, 'pending')
        self.pair(mine, self.sub(self.s2, self.qe), 'pending')
        self.assertEqual(self._voided(), set())

    def test_own_flag_on_another_question_does_not_void(self):
        self.behaviour(self.sub(self.s1, self.qm), 'pending')
        self.pair(self.sub(self.s1, self.qe), self.sub(self.s2, self.qe), 'confirmed')
        self.assertEqual(self._voided(), set())

    def test_similarity_pair_below_threshold_does_not_void(self):
        mine = self.sub(self.s1, self.qe)
        self.behaviour(mine, 'pending')
        self.pair(mine, self.sub(self.s2, self.qe), 'confirmed', flagged=False)
        self.assertEqual(self._voided(), set())


class WithheldPointsTest(_Scenario, TestCase):

    def setUp(self):
        self.make()
        self.s1, self.s2, self.s3 = self.student('w1'), self.student('w2'), self.student('w3')
        self.behaviour(self.sub(self.s1, self.qe, seconds=10), 'confirmed')   # voided: 10 withheld
        self.sub(self.s1, self.qm, seconds=100)
        self.sub(self.s2, self.qe, seconds=50)
        self.sub(self.s2, self.qm, seconds=50)
        self.behaviour(self.sub(self.s3, self.qm, 'failed'), 'confirmed')   # voided, but nothing solved
        self.subs = Submission.objects.filter(exam=self.exam)

    def test_points_by_student_excludes_voided_questions(self):
        self.assertEqual(metrics.points_by_student(self.subs), {self.s1.id: 20, self.s2.id: 30})

    def test_withheld_points(self):
        self.assertEqual(metrics.withheld_points(self.subs), {(self.s1.id, self.qe.id): 10})
        self.assertEqual(metrics.points_withheld_by_student(self.subs), {self.s1.id: 10})

    def test_scores_for_and_cohort_scores_follow(self):
        ids = [self.s1.id, self.s2.id, self.s3.id]
        expected = {self.s1.id: 20, self.s2.id: 30, self.s3.id: 0}
        self.assertEqual(metrics.scores_for(ids, self.subs), expected)
        self.assertEqual(metrics.cohort_scores('Gamma'), expected)
        self.assertEqual({k: v for k, v in metrics.all_scores().items() if k in ids}, expected)

    def test_solve_times_ignore_voided_questions(self):
        times = metrics.solve_times(self.subs)
        self.assertEqual(times[self.s1.id], 100)   # the voided 10s pass is left out
        self.assertEqual(times[self.s2.id], 50)

    def test_difficulty_progress_points_leave_out_withheld(self):
        easy = metrics.difficulty_progress(self.s1)['easy']
        self.assertEqual((easy['solved'], easy['points'], easy['withheld']), (0, 0, 10))   # voided: not solved either

    def test_under_review_is_any_pending_flag(self):
        pending = self.sub(self.s2, self.qe, 'failed')
        self.behaviour(pending, 'pending')
        self.assertEqual(metrics.under_review(self.subs), {self.s2.id})

    def test_under_review_counts_either_side_of_a_pending_pair(self):
        self.pair(self.sub(self.s2, self.qe), self.sub(self.s3, self.qe), 'pending')
        self.assertEqual(metrics.under_review(self.subs), {self.s2.id, self.s3.id})

    def test_reviewed_flags_are_not_under_review(self):
        self.assertEqual(metrics.under_review(self.subs), set())


class ReportIntegrityStatusTest(_Scenario, TestCase):
    """The exam report's per-student status: withheld, under review, or none."""

    def setUp(self):
        self.make()
        self.api = APIClient()
        self.api.force_authenticate(user=self.trainer)
        self.withheld, self.review, self.clean, self.matched = (
            self.student('w_withheld'), self.student('w_review'), self.student('w_clean'), self.student('w_matched'))
        mine = self.sub(self.withheld, self.qm)
        self.behaviour(mine, 'pending')
        self.pair(mine, self.sub(self.matched, self.qm), 'confirmed')   # matched: no own flag, keeps points
        self.sub(self.withheld, self.qe)
        self.behaviour(self.sub(self.review, self.qe), 'pending')
        self.sub(self.clean, self.qe)

    def _rows(self):
        res = self.api.get(f'/api/dashboard/exams/{self.exam.id}/')
        self.assertEqual(res.status_code, 200)
        return {s['student_id']: s for s in res.data['students']}

    def test_withheld_student(self):
        row = self._rows()[self.withheld.id]
        self.assertEqual((row['integrity_status'], row['points_withheld'], row['points']), ('withheld', 20, 10))

    def test_withheld_takes_precedence_over_a_pending_flag(self):
        self.behaviour(self.sub(self.withheld, self.qe, 'failed'), 'pending')
        self.assertEqual(self._rows()[self.withheld.id]['integrity_status'], 'withheld')

    def test_under_review_student_keeps_points(self):
        row = self._rows()[self.review.id]
        self.assertEqual((row['integrity_status'], row['points_withheld'], row['points']), ('under_review', 0, 10))

    def test_clean_and_matched_students_have_no_status(self):
        rows = self._rows()
        self.assertEqual((rows[self.clean.id]['integrity_status'], rows[self.clean.id]['points_withheld']), (None, 0))
        self.assertEqual((rows[self.matched.id]['integrity_status'], rows[self.matched.id]['points']), (None, 20))

    def test_rank_reflects_withheld_points(self):
        rows = self._rows()
        self.assertEqual(rows[self.matched.id]['rank'], 1)   # 20 points
        self.assertGreater(rows[self.withheld.id]['rank'], 1)   # 30 earned, 20 withheld -> 10


class ConfirmDropsEverywhereTest(_Scenario, TestCase):
    """After a trainer confirms, the student's points and rank drop identically on the exam
    report, the student page, My results, Home stats and the leaderboard, with no caching."""

    def setUp(self):
        self.make()
        self.api = APIClient()
        self.g1, self.g2, self.g3 = self.student('g1'), self.student('g2'), self.student('g3')
        for q in (self.qe, self.qm):
            self.sub(self.g1, q, seconds=60)
        self.sub(self.g2, self.qe, seconds=30)
        self.flag = self.behaviour(self.sub(self.g2, self.qm, seconds=30), 'pending')
        self.sub(self.g3, self.qe, seconds=90)

    def _as(self, user, url):
        self.api.force_authenticate(user=user)
        res = self.api.get(url)
        self.assertEqual(res.status_code, 200, url)
        return res.data

    def _everywhere(self, student):
        """(points, rank, withheld) from every page that shows them."""
        report = next(s for s in self._as(self.trainer, f'/api/dashboard/exams/{self.exam.id}/')['students']
                      if s['student_id'] == student.id)
        page = self._as(self.trainer, f'/api/dashboard/students/{student.id}/')['student']
        board = next(s for s in self._as(self.trainer, '/api/leaderboard/?cohort=Gamma')['leaderboard']
                     if s['student_id'] == student.id)
        home = self._as(student, '/api/leaderboard/me/')
        mine = next(e for e in self._as(student, '/api/leaderboard/me/exams/') if e['exam_id'] == self.exam.id)
        return {
            'exam report': (report['points'], report['rank'], report['points_withheld']),
            'student page': (page['score'], page['cohort_rank'], page['points_withheld']),
            'my results': (mine['points'], mine['rank'], mine['points_withheld']),
            'home': (home['score'], home['rank'], home['points_withheld']),
            'leaderboard': (board['score'], board['rank'], None),
        }

    def _assert(self, student, points, rank, withheld):
        for name, (p, r, w) in self._everywhere(student).items():
            with self.subTest(student=student.username, source=name):
                self.assertEqual((p, r), (points, rank))
                if w is not None:
                    self.assertEqual(w, withheld)

    def test_pending_flag_changes_nothing_but_marks_under_review(self):
        self._assert(self.g2, 30, 1, 0)   # faster than g1 on equal points
        self._assert(self.g1, 30, 2, 0)
        report = {s['student_id']: s for s in self._as(self.trainer, f'/api/dashboard/exams/{self.exam.id}/')['students']}
        self.assertEqual(report[self.g2.id]['integrity_status'], 'under_review')

    def test_confirming_drops_points_and_rank_everywhere(self):
        self.api.force_authenticate(user=self.trainer)
        res = self.api.patch(f'/api/plagiarism/behavioural/{self.flag.id}/review/',
                             {'review_status': 'confirmed', 'review_note': 'Pasted'}, format='json')
        self.assertEqual(res.status_code, 200)
        self._assert(self.g1, 30, 1, 0)
        self._assert(self.g2, 10, 2, 20)   # ties g3 on 10; the voided 30s pass no longer counts, g2's qe is faster
        self._assert(self.g3, 10, 3, 0)
        report = {s['student_id']: s for s in self._as(self.trainer, f'/api/dashboard/exams/{self.exam.id}/')['students']}
        self.assertEqual(report[self.g2.id]['integrity_status'], 'withheld')

    def test_student_pages_mark_the_withheld_question(self):
        self.flag.review_status = 'confirmed'
        self.flag.save()
        mine = next(e for e in self._as(self.g2, '/api/leaderboard/me/exams/') if e['exam_id'] == self.exam.id)
        qs = {q['question_id']: q for q in mine['questions']}
        self.assertEqual((qs[self.qm.id]['points_withheld'], qs[self.qe.id]['points_withheld']), (20, 0))
        page = self._as(self.trainer, f'/api/dashboard/students/{self.g2.id}/')
        q_rows = {q['question_id']: q for q in page['questions']}
        self.assertEqual((q_rows[self.qm.id]['points_withheld'], q_rows[self.qe.id]['points_withheld']), (20, 0))
        trend = next(p for p in page['performance_trend'] if p['exam'] == self.exam.title)
        self.assertEqual((trend['points'], trend['points_withheld']), (10, 20))

    def test_leaderboard_shows_no_integrity_markers(self):
        self.flag.review_status = 'confirmed'
        self.flag.save()
        for user in (self.trainer, self.g1):
            for entry in self._as(user, '/api/leaderboard/')['leaderboard']:
                with self.subTest(viewer=user.username, student=entry['username']):
                    self.assertNotIn('points_withheld', entry)
                    self.assertNotIn('integrity_status', entry)


# ── A voided question is not SOLVED: the pass rule and every rate follow ─────────
# Owner decision 2026-10-08: a question whose points are withheld for confirmed plagiarism
# no longer counts as solved, so it can drop the student below half and fail the exam.

class VoidedNotSolvedTest(_Scenario, TestCase):
    """exam_results: solved leaves voided questions out; `voided` counts the solved ones lost."""

    def setUp(self):
        self.make()
        self.s1 = self.student('n1')

    def _result(self, student=None):
        rows = metrics.exam_results(Submission.objects.filter(exam=self.exam))
        return next(r for r in rows if r['student_id'] == (student or self.s1).id)

    def test_voided_question_is_not_solved(self):
        self.sub(self.s1, self.qe)
        self.behaviour(self.sub(self.s1, self.qm), 'confirmed')
        r = self._result()
        self.assertEqual((r['solved'], r['voided'], r['total'], r['passed']), (1, 1, 2, True))

    def test_exam_fails_when_voiding_drops_below_half(self):
        self.behaviour(self.sub(self.s1, self.qe), 'confirmed')   # 1 of 2 solved, and it is voided
        r = self._result()
        self.assertEqual((r['solved'], r['voided'], r['passed']), (0, 1, False))

    def test_three_of_four_with_one_voided_still_passes(self):
        qs = [self.qe, self.qm] + [Question.objects.create(exam=self.exam, title=f'Q{i}', description='d',
                                                           difficulty='easy') for i in (3, 4)]
        for q in qs[:3]:
            self.sub(self.s1, q)
        self.behaviour(Submission.objects.get(student=self.s1, question=qs[0]), 'confirmed')
        r = self._result()
        self.assertEqual((r['solved'], r['voided'], r['total'], r['passed']), (2, 1, 4, True))
        self.behaviour(Submission.objects.get(student=self.s1, question=qs[1]), 'confirmed')
        r = self._result()
        self.assertEqual((r['solved'], r['voided'], r['passed']), (1, 2, False))

    def test_voided_question_never_solved_costs_nothing(self):
        self.sub(self.s1, self.qe)
        self.behaviour(self.sub(self.s1, self.qm, 'failed'), 'confirmed')
        r = self._result()
        self.assertEqual((r['solved'], r['voided'], r['passed']), (1, 0, True))

    def test_dismissing_restores_the_solve(self):
        flag = self.behaviour(self.sub(self.s1, self.qe), 'confirmed')
        self.assertFalse(self._result()['passed'])
        flag.review_status = 'dismissed'
        flag.save()
        r = self._result()
        self.assertEqual((r['solved'], r['voided'], r['passed']), (1, 0, True))

    def test_matched_only_student_keeps_the_solve(self):
        s2 = self.student('n2')
        mine = self.sub(self.s1, self.qe)
        self.behaviour(mine, 'confirmed')
        self.pair(mine, self.sub(s2, self.qe), 'confirmed')
        r = self._result(s2)
        self.assertEqual((r['solved'], r['voided'], r['passed']), (1, 0, True))

    def test_question_success_leaves_the_voided_student_out_of_solved(self):
        s2 = self.student('n2')
        self.behaviour(self.sub(self.s1, self.qe), 'confirmed')
        self.sub(s2, self.qe)
        row = metrics.question_success_by(Submission.objects.filter(exam=self.exam))[self.qe.id]
        self.assertEqual((row['solved_students'], row['attempted_students'], row['accepted_rate']), (1, 2, 50.0))
        grouped = metrics.question_success_by(Submission.objects.filter(exam=self.exam), 'exam_id')
        self.assertEqual(grouped[(self.exam.id, self.qe.id)]['solved_students'], 1)

    def test_success_rate_counts_the_failed_exam(self):
        s2 = self.student('n2')
        self.behaviour(self.sub(self.s1, self.qe), 'confirmed')
        self.sub(s2, self.qe)
        subs = Submission.objects.filter(exam=self.exam)
        self.assertEqual(metrics.success(subs), {'passed': 1, 'taken': 2, 'accepted_rate': 50.0})
        self.assertEqual(metrics.success_by(subs, 'student_id')[self.s1.id]['accepted_rate'], 0.0)


class VoidedFailsEverywhereTest(_Scenario, TestCase):
    """Every page that shows an exam result or a success rate agrees once a voided question
    drops a student below half, and explains it; dismissing the flag restores it everywhere.

        voided   solved QM only, confirmed behaviour flag on it -> 0 of 2, not passed
        partly   solved QE and QM, QM confirmed               -> 1 of 2, passed, 1 not counted
        matched  solved QM, confirmed pair with voided only   -> 1 of 2, passed
        clean    solved QE                                    -> 1 of 2, passed
    """

    def setUp(self):
        self.make()
        self.api = APIClient()
        self.v, self.p, self.m, self.c = (self.student(n) for n in ('v_voided', 'v_partly', 'v_matched', 'v_clean'))
        v_m = self.sub(self.v, self.qm)
        self.flag = self.behaviour(v_m, 'confirmed')
        self.sub(self.p, self.qe)
        self.behaviour(self.sub(self.p, self.qm), 'confirmed')
        self.pair(v_m, self.sub(self.m, self.qm), 'confirmed')
        self.sub(self.c, self.qe)

    def _as(self, user, url):
        self.api.force_authenticate(user=user)
        res = self.api.get(url)
        self.assertEqual(res.status_code, 200, url)
        return res.data

    def _per_exam(self, student):
        """(passed, questions_solved, questions_voided) from the report, the student page trend and My results."""
        report = next(s for s in self._as(self.trainer, f'/api/dashboard/exams/{self.exam.id}/')['students']
                      if s['student_id'] == student.id)
        trend = next(p for p in self._as(self.trainer, f'/api/dashboard/students/{student.id}/')['performance_trend']
                     if p['exam'] == self.exam.title)
        mine = next(e for e in self._as(student, '/api/leaderboard/me/exams/') if e['exam_id'] == self.exam.id)
        return {
            'exam report': (report['passed'], report['questions_solved'], report['questions_voided']),
            'student page trend': (trend['status'] == 'passed', trend['questions_solved'], trend['questions_voided']),
            'my results': (mine['passed'], mine['questions_solved'], mine['questions_voided']),
        }

    def _student_rate(self, student):
        students = {s['student_id']: s for s in self._as(self.trainer, '/api/dashboard/students/')}
        page = self._as(self.trainer, f'/api/dashboard/students/{student.id}/')['student']
        board = {s['student_id']: s for s in self._as(self.trainer, '/api/leaderboard/')['leaderboard']}
        me = self._as(student, '/api/leaderboard/me/')
        return {'students list': students[student.id]['accepted_rate'], 'student page': page['accepted_rate'],
                'leaderboard': board[student.id]['accepted_rate'], 'my stats': me['accepted_rate']}

    def _assert_per_exam(self, student, expected):
        for name, got in self._per_exam(student).items():
            with self.subTest(student=student.username, source=name):
                self.assertEqual(got, expected)

    def test_each_student_result_identical_on_every_page(self):
        self._assert_per_exam(self.v, (False, 0, 1))
        self._assert_per_exam(self.p, (True, 1, 1))
        self._assert_per_exam(self.m, (True, 1, 0))
        self._assert_per_exam(self.c, (True, 1, 0))

    def test_student_success_rate_identical_and_needing_help(self):
        for name, rate in self._student_rate(self.v).items():
            with self.subTest(source=name):
                self.assertEqual(rate, 0.0)
        help_rows = {r['student_id']: r for r in self._as(self.trainer, '/api/dashboard/health/')['students_needing_help']}
        self.assertEqual(help_rows[self.v.id]['accepted_rate'], 0.0)
        for name, rate in self._student_rate(self.m).items():
            with self.subTest(source=name):
                self.assertEqual(rate, 100.0)

    def test_exam_and_question_success_identical_on_every_page(self):
        history = next(r for r in self._as(self.trainer, '/api/dashboard/exams/') if r['exam_id'] == self.exam.id)
        detail = self._as(self.trainer, f'/api/dashboard/exams/{self.exam.id}/')
        overview = next(r for r in self._as(self.trainer, '/api/dashboard/health/')['exams'] if r['exam_id'] == self.exam.id)
        for name, payload in {'exam history row': history, 'exam detail': detail, 'overview exam row': overview}.items():
            with self.subTest(source=name):
                self.assertEqual((payload['passed_students'], payload['accepted_rate']), (3, 75.0))
                self.assertEqual((payload['hardest_question'], payload['hardest_accepted_rate']), ('QM', 33.3))
        qm = next(q for q in detail['questions'] if q['title'] == 'QM')
        self.assertEqual((qm['solved_students'], qm['attempted_students']), (1, 3))

    def test_my_results_question_keeps_the_raw_pass(self):
        mine = next(e for e in self._as(self.p, '/api/leaderboard/me/exams/') if e['exam_id'] == self.exam.id)
        qs = {q['title']: q for q in mine['questions']}
        self.assertEqual((qs['QM']['status'], qs['QM']['passed_on'], qs['QM']['voided']), ('passed', 1, True))
        self.assertEqual((qs['QE']['status'], qs['QE']['voided']), ('passed', False))

    def test_dismissing_the_flag_restores_the_pass_everywhere(self):
        self.api.force_authenticate(user=self.trainer)
        res = self.api.patch(f'/api/plagiarism/behavioural/{self.flag.id}/review/',
                             {'review_status': 'dismissed', 'review_note': 'Typed it'}, format='json')
        self.assertEqual(res.status_code, 200)
        self._assert_per_exam(self.v, (True, 1, 0))
        for name, rate in self._student_rate(self.v).items():
            with self.subTest(source=name):
                self.assertEqual(rate, 100.0)


from support.tests_appeals import AppealScenario   # noqa: E402  (shared appeal fixture)


class OverturnRestoresPassTest(AppealScenario, TestCase):
    """The classmate solved only QM, voided by the confirmed case: not passed. Overturning their
    appeal dismisses their flag, so QM counts again and the exam is passed."""

    def setUp(self):
        self.make()

    def _mine(self, student):
        res = self.api(student).get('/api/leaderboard/me/exams/')
        return next(e for e in res.data if e['exam_id'] == self.exam.id)

    def test_overturn_restores_the_pass(self):
        mine = self._mine(self.b)
        self.assertEqual((mine['passed'], mine['questions_solved'], mine['questions_voided']), (False, 0, 1))
        self.rule(self.file(self.b).data['id'], 'overturn')
        mine = self._mine(self.b)
        self.assertEqual((mine['passed'], mine['questions_solved'], mine['questions_voided']), (True, 1, 0))

    def test_upheld_keeps_the_fail(self):
        self.rule(self.file(self.b).data['id'], 'uphold')
        self.assertFalse(self._mine(self.b)['passed'])
