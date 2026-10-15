from django.db import IntegrityError, transaction
from django.test import TestCase, TransactionTestCase

from jobs.models import Job
from jobs.services import enqueue


class EnqueueTest(TestCase):
    def test_enqueue_creates_pending_job(self):
        with transaction.atomic():
            job = enqueue(Job.KIND_EXECUTE, 42)
        job.refresh_from_db()
        self.assertEqual(job.status, 'pending')
        self.assertEqual(job.attempt, 0)
        self.assertEqual(job.subject_id, 42)
        self.assertIsNone(job.published_at)

    def test_one_active_job_per_subject(self):
        with transaction.atomic():
            enqueue(Job.KIND_EXECUTE, 7)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                enqueue(Job.KIND_EXECUTE, 7)

    def test_a_new_job_is_allowed_after_the_previous_one_finished(self):
        with transaction.atomic():
            first = enqueue(Job.KIND_EXECUTE, 8)
        Job.objects.filter(pk=first.pk).update(status='succeeded')
        with transaction.atomic():
            second = enqueue(Job.KIND_EXECUTE, 8)
        self.assertNotEqual(first.pk, second.pk)


class EnqueueOutsideTransactionTest(TransactionTestCase):
    """TransactionTestCase runs in autocommit, so in_atomic_block is genuinely False here."""

    def test_enqueue_outside_transaction_is_refused(self):
        with self.assertRaises(RuntimeError):
            enqueue(Job.KIND_EXECUTE, 1)
        self.assertEqual(Job.objects.count(), 0)


class StatusPollIndexTest(TestCase):
    def test_the_status_poll_lookup_can_use_the_subject_index(self):
        # GET /api/submissions/<id>/status/ runs this every 1-3 s per waiting student. The partial
        # unique index can't serve it (no status predicate), so it needs its own.
        from django.db import connection
        with connection.cursor() as cur:
            cur.execute('SET LOCAL enable_seqscan = off')  # a tiny test table would always seq-scan
        plan = Job.objects.filter(kind=Job.KIND_EXECUTE, subject_id=1).order_by('-created_at').explain()
        self.assertIn('jobs_job_subject_idx', plan)
