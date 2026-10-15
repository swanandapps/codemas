from datetime import timedelta
from io import StringIO

from django.core.management import call_command
from django.test import TestCase
from django.utils import timezone

from accounts.models import User
from exams.models import Exam, Question
from plagiarism.models import BehaviouralFlag, PlagiarismFlag, ReviewAuditLog
from submissions.models import Submission


class SettlePastReviewsTest(TestCase):
    """settle_past_reviews decides pending flags on ENDED exams the way a trainer would have:
    a high-confidence behaviour flag of a student in a code-match pair is confirmed, a pair is
    confirmed when either side's behaviour flag was; everything else is dismissed."""

    def setUp(self):
        now = timezone.now()
        self.trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.ended = Exam.objects.create(title='Past', created_by=self.trainer, start_time=now - timedelta(days=30),
                                         end_time=now - timedelta(days=29))
        self.live = Exam.objects.create(title='Now', created_by=self.trainer, is_active=True, start_time=now)
        q = Question.objects.create(exam=self.ended, title='Q', description='d')
        lq = Question.objects.create(exam=self.live, title='LQ', description='d')
        users = {n: User.objects.create_user(username=n, password='pw', role='student') for n in 'abcde'}

        def sub(user, question, exam):
            return Submission.objects.create(student=user, exam=exam, question=question, code='x',
                                             language='javascript', attempt_number=1, status='passed')
        s = {n: sub(u, q, self.ended) for n, u in users.items()}
        self.b_high_paired = BehaviouralFlag.objects.create(submission=s['a'], risk_score=0.8, confidence='high')
        self.b_medium_paired = BehaviouralFlag.objects.create(submission=s['b'], risk_score=0.5, confidence='medium')
        self.b_high_alone = BehaviouralFlag.objects.create(submission=s['e'], risk_score=0.8, confidence='high')
        self.p_with_confirmed = PlagiarismFlag.objects.create(submission_1=s['a'], submission_2=s['c'],
                                                              similarity_score=1.0, flagged=True)
        self.p_without = PlagiarismFlag.objects.create(submission_1=s['b'], submission_2=s['d'],
                                                       similarity_score=0.9, flagged=True)
        self.b_live = BehaviouralFlag.objects.create(submission=sub(users['a'], lq, self.live),
                                                     risk_score=0.8, confidence='high')

    def statuses(self):
        flags = [self.b_high_paired, self.b_medium_paired, self.b_high_alone, self.p_with_confirmed,
                 self.p_without, self.b_live]
        for f in flags:
            f.refresh_from_db()
        return [f.review_status for f in flags]

    def test_dry_run_changes_nothing(self):
        out = StringIO()
        call_command('settle_past_reviews', stdout=out)
        self.assertEqual(self.statuses(), ['pending'] * 6)
        self.assertIn('Dry run', out.getvalue())

    def test_decisions_follow_the_rule_and_live_exams_are_untouched(self):
        call_command('settle_past_reviews', '--yes', stdout=StringIO())
        self.assertEqual(self.statuses(),
                         ['confirmed', 'dismissed', 'dismissed', 'confirmed', 'dismissed', 'pending'])
        self.b_high_paired.refresh_from_db()
        self.assertIn('Points for this question are withheld', self.b_high_paired.review_note)
        self.assertEqual(self.b_high_paired.reviewed_by, self.trainer)
        self.b_medium_paired.refresh_from_db()
        self.assertEqual(self.b_medium_paired.review_note, '')   # dismissals carry no note to the student
        self.p_with_confirmed.refresh_from_db()   # c only matched: the pair's note must be true for c too
        self.assertNotIn('copy signals', self.p_with_confirmed.review_note)
        self.assertIn('matched a classmate', self.p_with_confirmed.review_note)

    def test_audit_entries_are_dated_after_the_exam_and_rerun_is_a_no_op(self):
        call_command('settle_past_reviews', '--yes', stdout=StringIO())
        logs = ReviewAuditLog.objects.all()
        self.assertEqual(logs.count(), 5)
        expected = self.ended.end_time + timedelta(days=1)
        self.assertTrue(all(abs((log.created_at - expected).total_seconds()) < 1 for log in logs))
        out = StringIO()
        call_command('settle_past_reviews', '--yes', stdout=out)
        self.assertEqual(ReviewAuditLog.objects.count(), 5)
        self.assertIn('Nothing to decide', out.getvalue())
