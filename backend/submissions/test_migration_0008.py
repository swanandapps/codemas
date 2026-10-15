"""Migration 0008 adds UNIQUE(student, question, attempt_number). Rows written by the old create view
(count() + 1 with no lock) may already break it; 0008 renumbers those groups first so migrate can't
fail on prod and stop the web deploy (its CMD is migrate && gunicorn)."""
from datetime import timedelta

from django.db import IntegrityError, connection, transaction
from django.db.migrations.executor import MigrationExecutor
from django.test import TransactionTestCase
from django.utils import timezone

BEFORE = [('submissions', '0007_submission_normalized_code')]
AFTER = [('submissions', '0008_submission_unique_attempt_per_question')]


class Migration0008RenumbersDuplicateAttemptsTest(TransactionTestCase):
    @staticmethod
    def state_at(executor, submissions_node):
        # every other app at its latest state (the real DB schema), submissions at the given node
        nodes = [n for n in executor.loader.graph.leaf_nodes() if n[0] != 'submissions'] + submissions_node
        return executor.loader.project_state(nodes).apps

    def setUp(self):
        executor = MigrationExecutor(connection)
        executor.migrate(BEFORE)
        executor.loader.build_graph()
        self.apps = self.state_at(executor, BEFORE)

    def tearDown(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(executor.loader.graph.leaf_nodes())

    def sub(self, student, question, attempt, minutes):
        Submission = self.apps.get_model('submissions', 'Submission')
        s = Submission.objects.create(student=student, exam=question.exam, question=question, code='x',
                                      language='python', attempt_number=attempt, status='failed')
        Submission.objects.filter(pk=s.pk).update(submitted_at=self.t0 + timedelta(minutes=minutes))
        return s.pk

    def test_duplicates_are_renumbered_by_time_and_clean_groups_are_untouched(self):
        User = self.apps.get_model('accounts', 'User')
        Exam = self.apps.get_model('exams', 'Exam')
        Question = self.apps.get_model('exams', 'Question')
        trainer = User.objects.create(username='t', role='trainer')
        alice = User.objects.create(username='alice', role='student')
        bob = User.objects.create(username='bob', role='student')
        exam = Exam.objects.create(title='E', created_by=trainer)
        q1 = Question.objects.create(exam=exam, title='Q1', description='d', difficulty='easy')
        q2 = Question.objects.create(exam=exam, title='Q2', description='d', difficulty='easy')
        self.t0 = timezone.now() - timedelta(hours=1)

        # alice/q1: the race wrote attempt 1 twice; a later attempt got 2
        a_first = self.sub(alice, q1, 1, 0)
        a_raced = self.sub(alice, q1, 1, 1)
        a_third = self.sub(alice, q1, 2, 5)
        # alice/q2: two rows with the same attempt and the same timestamp -> id breaks the tie
        tie_lo = self.sub(alice, q2, 2, 3)
        tie_hi = self.sub(alice, q2, 2, 3)
        # bob/q1: no duplicates, but a gap (1, 3) and out-of-time-order numbers: left exactly as is
        b_one = self.sub(bob, q1, 3, 0)
        b_two = self.sub(bob, q1, 1, 2)

        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(AFTER)

        Submission = self.state_at(executor, AFTER).get_model('submissions', 'Submission')
        n = dict(Submission.objects.values_list('pk', 'attempt_number'))
        self.assertEqual([n[a_first], n[a_raced], n[a_third]], [1, 2, 3])
        self.assertEqual([n[tie_lo], n[tie_hi]], [1, 2])
        self.assertEqual([n[b_one], n[b_two]], [3, 1])

        # and the constraint is now in force
        with self.assertRaises(IntegrityError), transaction.atomic():
            Submission.objects.create(student_id=bob.pk, exam_id=exam.pk, question_id=q1.pk, code='x',
                                      language='python', attempt_number=1)

    def test_reverse_is_a_noop_that_drops_the_constraint(self):
        executor = MigrationExecutor(connection)
        executor.loader.build_graph()
        executor.migrate(AFTER)
        executor.loader.build_graph()
        executor.migrate(BEFORE)  # must not raise
