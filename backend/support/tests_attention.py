"""
Attention signals: what's new for a student since they last looked at their integrity
results, and what's waiting for a trainer.

Student: a decision is new when a trainer decided one of the student's flags (confirmed, or
dismissed with a note: what My results shows) after integrity_seen_at; a ruling is new when
the student's appeal was ruled on after it. Visiting My results or Disputes sets it to now.
Trainer: open appeals, and cases to decide across exams (the Investigation count).
"""
from datetime import timedelta

from django.test import TestCase
from django.utils import timezone

from accounts.models import User

from .tests_appeals import AppealScenario


class StudentAttentionTest(AppealScenario, TestCase):

    def setUp(self):
        self.make()
        # everything in the scenario was decided before the student last looked
        User.objects.filter(pk__in=[self.a.id, self.b.id, self.c.id]).update(
            integrity_seen_at=timezone.now() - timedelta(minutes=5))
        self.c_flag = self.behaviour(self.sub(self.c, self.qm, 'failed'), 'pending')

    def attention(self, user):
        res = self.api(user).get('/api/support/attention/')
        self.assertEqual(res.status_code, 200)
        return res.data

    def review(self, flag, review_status, note=''):
        return self.api(self.trainer).patch(f'/api/plagiarism/behavioural/{flag.id}/review/',
                                            {'review_status': review_status, 'review_note': note}, format='json')

    def test_nothing_new_and_pending_flags_stay_hidden(self):
        data = self.attention(self.c)
        self.assertEqual((data['new_decisions'], data['new_rulings'], data['latest']), (0, 0, None))

    def test_a_decision_after_the_last_visit_is_new_until_seen(self):
        self.review(self.c_flag, 'confirmed', 'Pasted.')
        data = self.attention(self.c)
        self.assertEqual(data['new_decisions'], 1)
        self.assertEqual((data['latest']['kind'], data['latest']['exam_id'], data['latest']['exam_title']),
                         ('decision', self.exam.id, 'Week 5'))
        res = self.api(self.c).post('/api/support/attention/seen/')
        self.assertEqual(res.status_code, 200)
        data = self.attention(self.c)
        self.assertEqual((data['new_decisions'], data['latest']), (0, None))

    def test_a_dismissal_without_a_note_is_not_shown_so_not_new(self):
        self.review(self.c_flag, 'dismissed')
        self.assertEqual(self.attention(self.c)['new_decisions'], 0)
        self.review(self.c_flag, 'dismissed', 'Checked: your own work.')
        self.assertEqual(self.attention(self.c)['new_decisions'], 1)

    def test_never_seen_counts_every_logged_decision(self):
        User.objects.filter(pk=self.c.id).update(integrity_seen_at=None)
        self.review(self.c_flag, 'confirmed', 'Pasted.')
        self.assertEqual(self.attention(self.c)['new_decisions'], 1)

    def test_several_flags_on_one_exam_are_one_new_decision(self):
        second = self.behaviour(self.sub(self.c, self.qm, 'failed'), 'pending')
        self.review(self.c_flag, 'confirmed', 'Pasted.')
        self.review(second, 'confirmed', 'Pasted.')
        self.assertEqual(self.attention(self.c)['new_decisions'], 1)

    def test_a_ruling_is_new_and_its_flag_changes_are_not_a_second_item(self):
        appeal_id = self.file(self.a).data['id']
        self.assertEqual(self.attention(self.a)['new_rulings'], 0)   # filing is the student's own act
        self.rule(appeal_id, 'overturn', 'Fair.')
        data = self.attention(self.a)
        self.assertEqual((data['new_rulings'], data['new_decisions']), (1, 0))
        self.assertEqual((data['latest']['kind'], data['latest']['status'], data['latest']['appeal_id'],
                          data['latest']['exam_title']), ('ruling', 'overturned', appeal_id, 'Week 5'))
        self.api(self.a).post('/api/support/attention/seen/')
        self.assertEqual(self.attention(self.a)['new_rulings'], 0)

    def test_the_latest_item_is_the_newest(self):
        appeal_id = self.file(self.a).data['id']
        self.rule(appeal_id, 'uphold', 'It stands.')
        self.assertEqual(self.attention(self.a)['latest']['status'], 'upheld')

    def test_trainers_do_not_mark_seen(self):
        self.assertEqual(self.api(self.trainer).post('/api/support/attention/seen/').status_code, 403)


class TrainerAttentionTest(AppealScenario, TestCase):

    def setUp(self):
        self.make()

    def attention(self):
        return self.api(self.trainer).get('/api/support/attention/').data

    def test_open_appeals_count_only_open_ones(self):
        self.file(self.a)
        ruled = self.file(self.b).data['id']
        self.rule(ruled, 'uphold')
        self.assertEqual(self.attention()['open_appeals'], 1)

    def test_cases_to_decide_match_the_case_files(self):
        self.assertEqual(self.attention()['cases_to_decide'], 0)   # everything decided
        self.behaviour(self.sub(self.c, self.qm, 'failed'), 'pending')
        d1, d2 = self.student('d1'), self.student('d2')
        from plagiarism.models import PlagiarismFlag
        PlagiarismFlag.objects.create(submission_1=self.sub(d1, self.qe), submission_2=self.sub(d2, self.qe),
                                      similarity_score=0.9, flagged=True)
        per_exam = self.api(self.trainer).get(f'/api/plagiarism/cohorts/{self.exam.id}/').data['stats']['cases_to_decide']
        self.assertEqual(per_exam, 2)
        self.assertEqual(self.attention()['cases_to_decide'], per_exam)
