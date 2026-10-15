"""
One-round appeals: a student responds once per exam to a confirmed plagiarism decision,
and a trainer upholds or overturns it.

Scenario (section Gamma, one ended exam): qe easy (10 points), qm medium (20 points)
    a (appellant): qe passed, qm passed; confirmed behaviour flag on qm; confirmed pair with b on qm
    b (classmate):  qm passed; confirmed behaviour flag on qm (same case as a)
    c (clean):      qe passed, no flags
    outsider:       never took the exam

    a: 10 points, 20 withheld · b: 0 points, 20 withheld · c: 10 points
Overturning a's appeal dismisses a's own behaviour flags only: the pair stays confirmed, so
by the voided-pairs rule a gets the 20 back while b, who keeps a confirmed behaviour flag,
stays withheld.
"""
import importlib
from datetime import timedelta

from django.apps import apps as django_apps
from django.test import TestCase
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, ExamEnrollment, Question
from plagiarism.models import BehaviouralFlag, PlagiarismFlag, ReviewAuditLog
from submissions.models import Submission
from support.models import DisputeRequest


class AppealScenario:
    """Shared by the appeal and attention tests (not a TestCase, so it isn't collected twice)."""

    NOTE = 'Your code was pasted in.'

    def make(self):
        now = timezone.now()
        self.trainer = User.objects.create_user(username='trainer_a', password='pw', role='trainer')
        self.exam = Exam.objects.create(
            title='Week 5', created_by=self.trainer, duration_minutes=60,
            start_time=now - timedelta(days=2), end_time=now - timedelta(days=2) + timedelta(hours=1),
        )
        self.qe = Question.objects.create(exam=self.exam, title='QE', description='d', difficulty='easy')
        self.qm = Question.objects.create(exam=self.exam, title='QM', description='d', difficulty='medium')
        self.a, self.b, self.c = (self.student(n) for n in ('appellant', 'classmate', 'clean'))
        self.outsider = User.objects.create_user(username='outsider', password='pw', role='student', cohort='Gamma')
        self.sub(self.a, self.qe)
        self.a_m = self.sub(self.a, self.qm)
        self.b_m = self.sub(self.b, self.qm)
        self.sub(self.c, self.qe)
        self.a_flag = self.behaviour(self.a_m, 'confirmed', self.NOTE)
        self.b_flag = self.behaviour(self.b_m, 'confirmed', self.NOTE)
        self.pair = PlagiarismFlag.objects.create(
            submission_1=self.a_m, submission_2=self.b_m, similarity_score=0.97, flagged=True,
            review_status='confirmed', review_note=self.NOTE, reviewed_by=self.trainer,
        )

    def student(self, name):
        s = User.objects.create_user(username=name, password='pw', role='student', cohort='Gamma')
        ExamEnrollment.objects.create(exam=self.exam, student=s)
        return s

    def sub(self, student, question, status='passed'):
        n = Submission.objects.filter(student=student, question=question).count() + 1
        return Submission.objects.create(student=student, exam=self.exam, question=question, code='x',
                                         language='python', attempt_number=n, status=status,
                                         time_to_complete_seconds=60)

    def behaviour(self, sub, review_status, note=''):
        return BehaviouralFlag.objects.create(submission=sub, risk_score=0.7, confidence='high',
                                              review_status=review_status, review_note=note,
                                              reviewed_by=self.trainer if review_status != 'pending' else None)

    def api(self, user):
        c = APIClient()
        c.force_authenticate(user)
        return c

    def file(self, student, note='I wrote it myself.', exam=None):
        return self.api(student).post('/api/support/disputes/', {
            'exam_id': (exam or self.exam).id, 'student_note': note}, format='json')

    def rule(self, appeal_id, decision, note='Looked again.', by=None):
        return self.api(by or self.trainer).patch(f'/api/support/disputes/{appeal_id}/', {
            'decision': decision, 'resolution_note': note}, format='json')


class FilingTest(AppealScenario, TestCase):

    def setUp(self):
        self.make()

    def test_a_student_files_one_appeal_per_exam(self):
        res = self.file(self.a)
        self.assertEqual(res.status_code, 201, res.data)
        self.assertEqual((res.data['exam_id'], res.data['status']), (self.exam.id, 'open'))
        again = self.file(self.a, 'Second try')
        self.assertEqual(again.status_code, 400)
        self.assertIn('already', again.data['error'])
        self.assertEqual(DisputeRequest.objects.count(), 1)

    def test_the_trainers_note_is_kept_on_the_appeal(self):
        res = self.file(self.a)
        self.assertEqual(res.data['decision_note'], self.NOTE)   # the same note on the flag and the pair: once

    def test_needs_a_confirmed_decision_on_the_exam(self):
        res = self.file(self.c)   # took it, no flags
        self.assertEqual(res.status_code, 400)
        self.assertIn('decision', res.data['error'])

    def test_a_pending_or_dismissed_flag_is_not_a_decision_to_appeal(self):
        pending, dismissed = self.student('pending_s'), self.student('dismissed_s')
        self.behaviour(self.sub(pending, self.qe), 'pending')
        self.behaviour(self.sub(dismissed, self.qe), 'dismissed', 'Fine after all.')
        for s in (pending, dismissed):
            self.assertEqual(self.file(s).status_code, 400, s.username)

    def test_a_confirmed_pair_on_either_side_can_be_appealed(self):
        matched = self.student('matched')
        PlagiarismFlag.objects.create(submission_1=self.sub(self.c, self.qm), submission_2=self.sub(matched, self.qm),
                                      similarity_score=0.95, flagged=True, review_status='confirmed')
        self.assertEqual(self.file(matched).status_code, 201)

    def test_a_response_is_required_and_at_most_1000_characters(self):
        for note in ('', '   '):
            res = self.file(self.a, note)
            self.assertEqual(res.status_code, 400)
        self.assertEqual(self.file(self.a, 'x' * 1001).status_code, 400)
        self.assertFalse(DisputeRequest.objects.exists())
        self.assertEqual(self.file(self.a, 'x' * 1000).status_code, 201)

    def test_an_exam_the_student_did_not_take_is_not_found(self):
        self.assertEqual(self.file(self.outsider).status_code, 404)
        missing = Exam(id=987654)
        self.assertEqual(self.file(self.a, exam=missing).status_code, 404)

    def test_trainers_cannot_file(self):
        self.assertEqual(self.file(self.trainer).status_code, 403)


class RulingTest(AppealScenario, TestCase):

    def setUp(self):
        self.make()
        self.appeal_id = self.file(self.a).data['id']

    def statuses(self):
        return {f.id: f.review_status for f in BehaviouralFlag.objects.all()} | {
            ('pair', p.id): p.review_status for p in PlagiarismFlag.objects.all()}

    def test_a_reply_is_required(self):
        for note in ('', '  '):
            self.assertEqual(self.rule(self.appeal_id, 'uphold', note).status_code, 400)
        self.assertEqual(self.rule(self.appeal_id, 'maybe').status_code, 400)
        self.assertEqual(DisputeRequest.objects.get().status, 'open')

    def test_students_cannot_rule(self):
        self.assertEqual(self.rule(self.appeal_id, 'overturn', by=self.a).status_code, 403)

    def test_uphold_changes_no_flag_and_is_final(self):
        before = self.statuses()
        res = self.rule(self.appeal_id, 'uphold', 'The evidence stands.')
        self.assertEqual(res.status_code, 200, res.data)
        appeal = DisputeRequest.objects.get()
        self.assertEqual((appeal.status, appeal.resolution_note, appeal.resolved_by), ('upheld', 'The evidence stands.', self.trainer))
        self.assertIsNotNone(appeal.resolved_at)
        self.assertEqual(self.statuses(), before)
        again = self.rule(self.appeal_id, 'overturn')
        self.assertEqual(again.status_code, 400)
        self.assertEqual(DisputeRequest.objects.get().status, 'upheld')
        self.assertEqual(self.file(self.a).status_code, 400)   # no second appeal

    def test_overturn_dismisses_only_the_appellants_behaviour_flags(self):
        extra = self.behaviour(self.sub(self.a, self.qe, 'failed'), 'pending')
        res = self.rule(self.appeal_id, 'overturn', 'You showed your drafts.')
        self.assertEqual(res.status_code, 200, res.data)
        self.assertEqual(DisputeRequest.objects.get().status, 'overturned')
        for flag in (self.a_flag, extra):
            flag.refresh_from_db()
            self.assertEqual((flag.review_status, flag.review_note, flag.reviewed_by),
                             ('dismissed', 'You showed your drafts.', self.trainer))
            self.assertTrue(ReviewAuditLog.objects.filter(flag_type='behavioural', flag_id=flag.id,
                                                          action='dismissed', note='You showed your drafts.').exists())
        self.b_flag.refresh_from_db()
        self.pair.refresh_from_db()
        self.assertEqual((self.b_flag.review_status, self.pair.review_status), ('confirmed', 'confirmed'))
        self.assertEqual(self.rule(self.appeal_id, 'uphold').status_code, 400)   # final

    def test_overturn_restores_the_appellants_points_everywhere_and_not_the_classmates(self):
        def everywhere(student):
            report = next(s for s in self.api(self.trainer).get(f'/api/dashboard/exams/{self.exam.id}/').data['students']
                          if s['student_id'] == student.id)
            mine = next(e for e in self.api(student).get('/api/leaderboard/me/exams/').data if e['exam_id'] == self.exam.id)
            board = next(s for s in self.api(student).get('/api/leaderboard/?cohort=Gamma').data['leaderboard']
                         if s['student_id'] == student.id)
            return {'report': (report['points'], report['points_withheld']),
                    'my results': (mine['points'], mine['points_withheld']),
                    'leaderboard': (board['score'], None)}

        self.assertEqual(everywhere(self.a)['report'], (10, 20))
        self.rule(self.appeal_id, 'overturn')
        for source, (points, withheld) in everywhere(self.a).items():
            with self.subTest(student='appellant', source=source):
                self.assertEqual(points, 30)
                if withheld is not None:
                    self.assertEqual(withheld, 0)
        for source, (points, withheld) in everywhere(self.b).items():
            with self.subTest(student='classmate', source=source):
                self.assertEqual(points, 0)
                if withheld is not None:
                    self.assertEqual(withheld, 20)

    def test_a_legacy_appeal_without_an_exam_can_only_be_upheld(self):
        legacy = DisputeRequest.objects.create(student=self.b, flag_type='behavioural', flag_id=self.b_flag.id,
                                               student_note='old')
        self.assertEqual(self.rule(legacy.id, 'overturn').status_code, 400)
        self.assertEqual(self.rule(legacy.id, 'uphold').status_code, 200)


class TrainerListTest(AppealScenario, TestCase):

    def setUp(self):
        self.make()
        self.open_id = self.file(self.a, 'It was my own work.').data['id']
        self.ruled_id = self.file(self.b).data['id']
        self.rule(self.ruled_id, 'uphold')

    def rows(self, status=None):
        url = '/api/support/disputes/' + (f'?status={status}' if status else '')
        return self.api(self.trainer).get(url).data

    def test_filters_open_by_default(self):
        self.assertEqual([r['id'] for r in self.rows()], [self.open_id])
        self.assertEqual([r['id'] for r in self.rows('upheld')], [self.ruled_id])
        self.assertEqual(self.rows('overturned'), [])
        self.assertEqual({r['id'] for r in self.rows('all')}, {self.open_id, self.ruled_id})

    def test_a_row_names_the_student_exam_response_and_case(self):
        from plagiarism.views import case_keys, exam_cases
        row = self.rows()[0]
        self.assertEqual((row['student'], row['student_username'], row['exam_id'], row['exam_title']),
                         (self.a.id, 'appellant', self.exam.id, 'Week 5'))
        self.assertEqual((row['student_note'], row['decision_note']), ('It was my own work.', self.NOTE))
        self.assertEqual(row['case_key'], case_keys(exam_cases(self.exam.id)).get(self.a.id))

    def test_detail_has_the_decision_response_and_case(self):
        data = self.api(self.trainer).get(f'/api/support/disputes/{self.open_id}/').data
        self.assertEqual((data['exam_title'], data['decision_note'], data['student_note']),
                         ('Week 5', self.NOTE, 'It was my own work.'))
        self.assertIsNotNone(data['case_key'])

    def test_a_legacy_row_still_lists(self):
        legacy = DisputeRequest.objects.create(student=self.c, flag_type='behavioural', flag_id=self.a_flag.id,
                                               student_note='old', exam=None)
        row = next(r for r in self.rows('all') if r['id'] == legacy.id)
        self.assertEqual((row['exam_id'], row['case_key']), (None, None))
        self.assertEqual(row['flag_context']['exam'], 'Week 5')

    def test_students_cannot_list_everyones(self):
        self.assertEqual(self.api(self.a).get('/api/support/disputes/').status_code, 403)


class StudentListTest(AppealScenario, TestCase):

    def setUp(self):
        self.make()

    def test_a_student_sees_only_their_own_newest_first(self):
        first = self.file(self.a).data['id']
        self.file(self.b)
        other = Exam.objects.create(title='Week 6', created_by=self.trainer)
        q = Question.objects.create(exam=other, title='Q6', description='d')
        sub = Submission.objects.create(student=self.a, exam=other, question=q, code='x', language='python',
                                        attempt_number=1, status='passed')
        self.behaviour(sub, 'confirmed', 'Again.')
        second = self.file(self.a, exam=other).data['id']
        DisputeRequest.objects.filter(pk=first).update(created_at=timezone.now() - timedelta(days=1))
        self.rule(first, 'overturn', 'Fair enough.')
        rows = self.api(self.a).get('/api/support/disputes/mine/').data
        self.assertEqual([r['id'] for r in rows], [second, first])
        ruled = rows[1]
        self.assertEqual((ruled['exam_title'], ruled['status'], ruled['resolution_note'], ruled['decision_note']),
                         ('Week 5', 'overturned', 'Fair enough.', self.NOTE))

    def test_trainers_have_no_appeals_of_their_own(self):
        self.assertEqual(self.api(self.trainer).get('/api/support/disputes/mine/').status_code, 403)


class AppealOnTrainerPagesTest(AppealScenario, TestCase):
    """An open appeal shows on the exam's case file and on the student page's Integrity tab."""

    def setUp(self):
        self.make()
        self.appeal_id = self.file(self.a, 'Please look at my drafts.').data['id']

    def test_case_file_lists_open_appeals(self):
        data = self.api(self.trainer).get(f'/api/plagiarism/cohorts/{self.exam.id}/').data
        self.assertEqual([(x['id'], x['student_id'], x['student_note']) for x in data['appeals']],
                         [(self.appeal_id, self.a.id, 'Please look at my drafts.')])
        self.rule(self.appeal_id, 'uphold')
        self.assertEqual(self.api(self.trainer).get(f'/api/plagiarism/cohorts/{self.exam.id}/').data['appeals'], [])

    def test_student_page_integrity_group_carries_the_appeal(self):
        group = self.api(self.trainer).get(f'/api/dashboard/students/{self.a.id}/').data['integrity_cases'][0]
        self.assertEqual(group['appeal'], {'id': self.appeal_id, 'status': 'open', 'student_note': 'Please look at my drafts.'})
        other = self.api(self.trainer).get(f'/api/dashboard/students/{self.c.id}/').data['integrity_cases']
        self.assertEqual(other, [])

    def test_student_page_disputes_tab_names_the_exam(self):
        d = self.api(self.trainer).get(f'/api/dashboard/students/{self.a.id}/').data['disputes'][0]
        self.assertEqual((d['id'], d['exam_title'], d['status']), (self.appeal_id, 'Week 5', 'open'))


class StatusMigrationTest(AppealScenario, TestCase):
    """The data migration: per-flag disputes become per-exam appeals."""

    def setUp(self):
        self.make()
        self.migration = importlib.import_module('support.migrations.0002_appeals_per_exam')

    def legacy(self, status, flag_type='behavioural', flag_id=None):
        return DisputeRequest.objects.create(student=self.a, flag_type=flag_type,
                                             flag_id=flag_id or self.a_flag.id, student_note='n', status=status)

    def test_statuses_map_and_exams_backfill(self):
        resolved, escalated, still_open = self.legacy('resolved'), self.legacy('escalated'), self.legacy('open')
        pair = self.legacy('resolved', 'similarity', self.pair.id)
        lost = self.legacy('resolved', 'behavioural', 999999)
        counts = self.migration.migrate_appeals(django_apps)
        got = {d.id: (d.status, d.exam_id, d.decision_note) for d in DisputeRequest.objects.all()}
        self.assertEqual(got[resolved.id], ('upheld', self.exam.id, self.NOTE))
        self.assertEqual(got[escalated.id], ('open', self.exam.id, self.NOTE))
        self.assertEqual(got[still_open.id], ('open', self.exam.id, self.NOTE))
        self.assertEqual(got[pair.id], ('upheld', self.exam.id, self.NOTE))
        self.assertEqual(got[lost.id], ('upheld', None, ''))   # the flag is gone: kept for display, no exam
        self.assertEqual(counts, {'resolved_to_upheld': 3, 'escalated_to_open': 1, 'exam_backfilled': 4, 'exam_unresolved': 1})

    def test_reverse_maps_back(self):
        upheld, overturned = self.legacy('upheld'), self.legacy('overturned')
        self.migration.unmigrate_appeals(django_apps)
        self.assertEqual({d.id: d.status for d in DisputeRequest.objects.all()},
                         {upheld.id: 'resolved', overturned.id: 'resolved'})


class SeenAtMigrationTest(TestCase):
    """Existing accounts start with everything already seen, so old decisions don't light up as new."""

    def test_existing_users_get_seen_now(self):
        u = User.objects.create_user(username='old', password='pw', role='student')
        migration = importlib.import_module('accounts.migrations.0004_user_integrity_seen_at')
        migration.mark_existing_seen(django_apps, None)
        u.refresh_from_db()
        self.assertIsNotNone(u.integrity_seen_at)
