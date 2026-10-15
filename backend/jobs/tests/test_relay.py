import threading
from datetime import timedelta
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.db import connection, transaction
from django.test import TestCase, TransactionTestCase, override_settings
from django.utils import timezone
from rest_framework.test import APIClient

from accounts.models import User
from exams.models import Exam, ExamEnrollment, Question
from jobs.models import MAX_ATTEMPTS, Job
from jobs.relay import LOCAL_QUEUED_TOO_LONG, SQS_EXPIRED_LEASE_BACKSTOP, SQS_QUEUED_TOO_LONG, sweep_stuck, tick
from jobs.services import claim, enqueue, fail
from jobs.transports import Transport
from submissions.models import Submission


class FakeTransport(Transport):
    """Only implements publish(); the base class's publish_many() loops over it."""

    def __init__(self, fail_on=None):
        self.sent, self.fail_on = [], fail_on

    def publish(self, job):
        if job.subject_id == self.fail_on:
            raise ConnectionError('queue down')
        self.sent.append(job.subject_id)



def make(sid):
    with transaction.atomic():
        return enqueue(Job.KIND_EXECUTE, sid)


@override_settings(JOB_TRANSPORT='local')
class RelayTest(TestCase):
    make = staticmethod(make)

    def test_tick_publishes_pending_jobs_and_marks_them_queued(self):
        a, b = self.make(1), self.make(2)
        t = FakeTransport()
        self.assertEqual(tick(t), 2)
        self.assertEqual(sorted(t.sent), [1, 2])
        for j in (a, b):
            j.refresh_from_db()
            self.assertEqual(j.status, 'queued')
            self.assertIsNotNone(j.published_at)

    def test_tick_respects_the_batch_size_oldest_first(self):
        for sid in (1, 2, 3):
            self.make(sid)
        t = FakeTransport()
        self.assertEqual(tick(t, batch=2), 2)
        self.assertEqual(t.sent, [1, 2])
        self.assertEqual(tick(t, batch=2), 1)
        self.assertEqual(t.sent, [1, 2, 3])

    def test_tick_ignores_jobs_that_are_not_pending(self):
        j = self.make(1)
        for s in ('queued', 'running', 'succeeded', 'failed', 'dead'):
            Job.objects.filter(pk=j.pk).update(status=s)
            self.assertEqual(tick(FakeTransport()), 0, s)

    def test_a_failed_publish_leaves_the_job_pending_for_the_next_tick(self):
        a = self.make(3)
        self.assertEqual(tick(FakeTransport(fail_on=3)), 0)
        a.refresh_from_db()
        self.assertEqual(a.status, 'pending')
        self.assertIsNone(a.published_at)
        self.assertIn('queue down', a.last_error)
        t = FakeTransport()
        self.assertEqual(tick(t), 1)  # retried next tick
        self.assertEqual(t.sent, [3])
        a.refresh_from_db()
        self.assertEqual(a.status, 'queued')

    def test_a_publish_failure_keeps_the_handlers_error(self):
        a = self.make(3)
        Job.objects.filter(pk=a.pk).update(last_error="grader_error: OSError('disk full')")
        tick(FakeTransport(fail_on=3))
        tick(FakeTransport(fail_on=3))  # a second failure replaces the first note instead of piling up
        a.refresh_from_db()
        self.assertEqual(a.last_error, "grader_error: OSError('disk full')\n"
                                       "publish failed: ConnectionError('queue down')")
        tick(FakeTransport())
        a.refresh_from_db()
        self.assertEqual((a.status, a.last_error.splitlines()[0]), ('queued', "grader_error: OSError('disk full')"))

    def test_a_transport_that_crashes_outright_leaves_the_whole_batch_pending(self):
        a, b = self.make(1), self.make(2)

        class Broken(Transport):
            def publish_many(self, jobs):
                raise RuntimeError('bug')
        self.assertEqual(tick(Broken()), 0)
        self.assertEqual(set(Job.objects.filter(pk__in=[a.pk, b.pk]).values_list('status', flat=True)), {'pending'})
        a.refresh_from_db()
        self.assertIn('bug', a.last_error)

    def test_one_failed_publish_does_not_block_the_rest_of_the_batch(self):
        a, b = self.make(1), self.make(2)
        t = FakeTransport(fail_on=1)
        self.assertEqual(tick(t), 1)
        a.refresh_from_db(); b.refresh_from_db()
        self.assertEqual((a.status, b.status), ('pending', 'queued'))

    def test_sweep_requeues_expired_leases_and_kills_after_max_attempts(self):
        stuck, worn = self.make(4), self.make(5)
        past = timezone.now() - timedelta(minutes=1)
        Job.objects.filter(pk=stuck.pk).update(status='running', attempt=1, lease_expires_at=past)
        Job.objects.filter(pk=worn.pk).update(status='running', attempt=3, lease_expires_at=past)
        self.assertEqual(sweep_stuck(), {'requeued': 1, 'dead': 1})
        stuck.refresh_from_db(); worn.refresh_from_db()
        self.assertEqual((stuck.status, worn.status), ('pending', 'dead'))
        self.assertIsNone(stuck.lease_token)
        self.assertIsNone(stuck.lease_expires_at)
        self.assertEqual(stuck.attempt, 1)  # the next claim counts the attempt, not the sweep
        self.assertIsNotNone(worn.finished_at)
        self.assertIsNone(worn.lease_token)
        self.assertEqual(stuck.last_error, 'sweep: lease expired on attempt 1; requeued')
        self.assertEqual(worn.last_error, 'sweep: lease expired at max attempts (3/3); dead')

    def test_sweep_notes_are_appended_to_the_handlers_error(self):
        j = self.make(4)
        Job.objects.filter(pk=j.pk).update(status='running', attempt=1, last_error='boom',
                                           lease_expires_at=timezone.now() - timedelta(minutes=1))
        sweep_stuck()
        j.refresh_from_db()
        self.assertEqual(j.last_error, 'boom\nsweep: lease expired on attempt 1; requeued')

    def test_sweep_leaves_live_leases_and_terminal_jobs_alone(self):
        live, done = self.make(1), self.make(2)
        future = timezone.now() + timedelta(minutes=1)
        Job.objects.filter(pk=live.pk).update(status='running', attempt=1, lease_expires_at=future)
        Job.objects.filter(pk=done.pk).update(status='succeeded', lease_expires_at=timezone.now() - timedelta(days=1),
                                              published_at=timezone.now() - timedelta(days=1))
        self.assertEqual(sweep_stuck(), {'requeued': 0, 'dead': 0})
        live.refresh_from_db(); done.refresh_from_db()
        self.assertEqual((live.status, done.status), ('running', 'succeeded'))

    def test_sweep_republishes_jobs_queued_too_long(self):
        self.assertEqual(LOCAL_QUEUED_TOO_LONG, timedelta(minutes=10))
        j = self.make(6)
        Job.objects.filter(pk=j.pk).update(status='queued', published_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(sweep_stuck()['requeued'], 1)
        j.refresh_from_db()
        self.assertEqual(j.status, 'pending')
        self.assertEqual(j.last_error, 'sweep: queued 10 min with no claim; requeued')

    def test_sweep_leaves_recently_queued_jobs_alone(self):
        j = self.make(6)
        Job.objects.filter(pk=j.pk).update(status='queued', published_at=timezone.now() - timedelta(minutes=1))
        self.assertEqual(sweep_stuck(), {'requeued': 0, 'dead': 0})

    def test_a_job_released_by_fail_is_republished_by_the_next_tick(self):
        """/fail/ puts the job back in the outbox, so it doesn't wait for the sweep."""
        j = self.make(7)
        tick(FakeTransport())
        Job.objects.filter(pk=j.pk).update(status='running', attempt=1, lease_token='00000000-0000-0000-0000-000000000001',
                                           lease_expires_at=timezone.now() + timedelta(minutes=2))
        fail(j.pk, '00000000-0000-0000-0000-000000000001', 'boom')
        j.refresh_from_db()
        self.assertEqual(j.status, 'pending')
        t = FakeTransport()
        self.assertEqual(tick(t), 1)
        self.assertEqual(t.sent, [7])
        j.refresh_from_db()
        self.assertEqual((j.status, j.attempt, j.last_error), ('queued', 1, 'boom'))

    def test_sweep_recovers_queued_and_running_jobs_with_missing_timestamps(self):
        q, r = self.make(1), self.make(2)
        Job.objects.filter(pk=q.pk).update(status='queued', published_at=None)
        Job.objects.filter(pk=r.pk).update(status='running', attempt=1, lease_expires_at=None)
        self.assertEqual(sweep_stuck(), {'requeued': 2, 'dead': 0})

    def test_sweep_dead_on_a_deleted_submission_does_not_crash(self):
        j = self.make(999999)
        Job.objects.filter(pk=j.pk).update(status='running', attempt=MAX_ATTEMPTS,
                                           lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(sweep_stuck(), {'requeued': 0, 'dead': 1})


@override_settings(JOB_TRANSPORT='sqs')
class SqsSweepTest(TestCase):
    """With SQS the queue redelivers after the visibility timeout and its redrive policy decides when a
    message is dead, so the sweep must not race it: it only kills jobs at MAX_ATTEMPTS and republishes
    queued jobs much later."""
    make = staticmethod(make)

    def test_expired_lease_below_max_is_left_for_sqs_to_redeliver(self):
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        student = User.objects.create_user(username='s', password='pw', role='student')
        q = Question.objects.create(exam=Exam.objects.create(title='E', created_by=trainer), title='Q', description='d')
        sub = Submission.objects.create(student=student, exam=q.exam, question=q, code='x', language='python',
                                        attempt_number=1)
        j = self.make(sub.id)
        Job.objects.filter(pk=j.pk).update(status='running', attempt=1,
                                           lease_expires_at=timezone.now() - timedelta(minutes=5))
        self.assertEqual(sweep_stuck(), {'requeued': 0, 'dead': 0})
        j.refresh_from_db()
        self.assertEqual(j.status, 'running')
        # and the redelivered message may claim it: an expired lease is claimable
        claimed, _ = claim(j.pk)
        self.assertEqual((claimed.status, claimed.attempt), ('running', 2))

    def test_backstop_requeues_a_lease_expired_more_than_thirty_minutes_ago(self):
        """Deliveries that never claimed (409 busy, Django unreachable) don't spend attempts, so a message
        can reach the DLQ below MAX_ATTEMPTS and leave its job running. The backstop rescues it."""
        self.assertEqual(SQS_EXPIRED_LEASE_BACKSTOP, timedelta(minutes=30))
        recent, old = self.make(1), self.make(2)
        now = timezone.now()
        Job.objects.filter(pk=recent.pk).update(status='running', attempt=1, last_error='boom',
                                                lease_expires_at=now - timedelta(minutes=5))
        Job.objects.filter(pk=old.pk).update(status='running', attempt=1, last_error='boom',
                                             lease_expires_at=now - timedelta(minutes=31))
        self.assertEqual(sweep_stuck(now=now), {'requeued': 1, 'dead': 0})
        recent.refresh_from_db(); old.refresh_from_db()
        self.assertEqual(recent.status, 'running')
        self.assertEqual((old.status, old.lease_token, old.lease_expires_at, old.attempt), ('pending', None, None, 1))
        self.assertEqual(old.last_error, 'boom\nsweep: lease expired 30+ min ago; requeued by sweep backstop')

    def test_expired_lease_at_max_still_dies_and_marks_the_submission(self):
        j = self.make(1)
        Job.objects.filter(pk=j.pk).update(status='running', attempt=MAX_ATTEMPTS,
                                           lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(sweep_stuck(), {'requeued': 0, 'dead': 1})
        j.refresh_from_db()
        self.assertEqual((j.status, j.last_error), ('dead', 'sweep: lease expired at max attempts (3/3); dead'))

    def test_queued_threshold_is_thirty_minutes(self):
        self.assertEqual(SQS_QUEUED_TOO_LONG, timedelta(minutes=30))
        self.assertGreater(SQS_QUEUED_TOO_LONG, 3 * timedelta(seconds=540))  # maxReceiveCount x visibility
        j = self.make(1)
        Job.objects.filter(pk=j.pk).update(status='queued', published_at=timezone.now() - timedelta(minutes=11))
        self.assertEqual(sweep_stuck(), {'requeued': 0, 'dead': 0})
        Job.objects.filter(pk=j.pk).update(published_at=timezone.now() - timedelta(minutes=31))
        self.assertEqual(sweep_stuck(), {'requeued': 1, 'dead': 0})
        j.refresh_from_db()
        self.assertEqual((j.status, j.last_error), ('pending', 'sweep: queued 30 min with no claim; requeued'))


LOCMEM = {'default': {'BACKEND': 'django.core.cache.backends.locmem.LocMemCache'}}


@override_settings(PIPELINE_LANGUAGES={'python'}, CACHES=LOCMEM, JOB_TRANSPORT='local')  # locmem: keep throttle counters out of dev Redis
class SweepDeadSubmissionTest(TestCase):
    """A job the sweep kills leaves its submission in 'error' and gives the student the attempt back."""

    def setUp(self):
        trainer = User.objects.create_user(username='t', password='pw', role='trainer')
        self.student = User.objects.create_user(username='s', password='pw', role='student', cohort='C')
        exam = Exam.objects.create(title='E', created_by=trainer, duration_minutes=60, is_active=True,
                                   start_time=timezone.now() - timedelta(hours=1),
                                   end_time=timezone.now() + timedelta(hours=1))
        ExamEnrollment.objects.create(exam=exam, student=self.student)
        self.q = Question.objects.create(exam=exam, title='Q', description='d', difficulty='easy')
        self.api = APIClient()
        self.api.force_authenticate(self.student)

    def submit(self):
        return self.api.post('/api/submissions/create/', {'question': self.q.id, 'code': 'print(1)',
                                                          'language': 'python'}, format='json')

    def test_dead_job_marks_submission_error_and_frees_the_attempt(self):
        from plagiarism.models import PlagiarismPolicy
        max_attempts = PlagiarismPolicy.get().max_attempts
        ids = [self.submit().data['id'] for _ in range(max_attempts)]
        Job.objects.filter(subject_id__in=ids).update(status='succeeded')
        self.assertEqual(self.submit().status_code, 403)

        # the last attempt's job got stuck at MAX_ATTEMPTS
        Job.objects.filter(subject_id=ids[-1]).update(status='running', attempt=MAX_ATTEMPTS,
                                                      lease_expires_at=timezone.now() - timedelta(seconds=1))
        self.assertEqual(sweep_stuck(), {'requeued': 0, 'dead': 1})
        self.assertEqual(Submission.objects.get(pk=ids[-1]).status, 'error')
        self.assertEqual(self.submit().status_code, 201)


@override_settings(JOB_TRANSPORT='local')
class RunRelayCommandTest(TestCase):
    def test_once_publishes_sweeps_and_closes_the_transport(self):
        make(1)
        stuck = make(2)
        Job.objects.filter(pk=stuck.pk).update(status='running', attempt=1,
                                               lease_expires_at=timezone.now() - timedelta(seconds=1))
        t = FakeTransport()
        out = StringIO()
        # close_old_connections would close the TestCase's wrapping transaction (CONN_MAX_AGE=0)
        with mock.patch('jobs.management.commands.run_relay.get_transport', return_value=t), \
                mock.patch('jobs.management.commands.run_relay.close_old_connections'), \
                mock.patch.object(t, 'close') as close:
            call_command('run_relay', '--once', stdout=out)
        self.assertEqual(t.sent, [1])
        self.assertIn('published 1', out.getvalue())
        self.assertIn("'requeued': 1", out.getvalue())
        close.assert_called_once_with(wait=True)  # --once lets local handlers finish

    def test_the_loop_logs_an_error_and_keeps_going(self):
        t = FakeTransport()
        out, err = StringIO(), StringIO()
        with mock.patch('jobs.management.commands.run_relay.get_transport', return_value=t), \
                mock.patch('jobs.management.commands.run_relay.close_old_connections'), \
                mock.patch('jobs.management.commands.run_relay.time.sleep') as sleep, \
                mock.patch('jobs.management.commands.run_relay.sweep_stuck', return_value={'requeued': 0, 'dead': 0}), \
                mock.patch('jobs.management.commands.run_relay.tick',
                           side_effect=[RuntimeError('db down'), 2, KeyboardInterrupt]) as tick_, \
                mock.patch.object(t, 'close') as close:
            call_command('run_relay', stdout=out, stderr=err)
        self.assertEqual(tick_.call_count, 3)  # kept ticking after the error
        self.assertIn("relay: error RuntimeError('db down'); retrying", err.getvalue())
        self.assertIn('relay: published 2', out.getvalue())
        self.assertIn('relay: stopping', out.getvalue())
        self.assertEqual(sleep.call_count, 2)
        close.assert_called_once_with(wait=False)  # Ctrl-C doesn't wait on a backlog


class ConcurrentTickTest(TransactionTestCase):
    """SELECT ... FOR UPDATE SKIP LOCKED: two relays ticking at once never publish the same job."""

    def test_two_concurrent_ticks_never_publish_the_same_job(self):
        jobs = [make(sid) for sid in (1, 2, 3)]
        entered, release = threading.Event(), threading.Event()

        class Blocking(FakeTransport):
            def publish(self, job):
                super().publish(job)
                entered.set()
                release.wait(10)  # hold the row lock while the other relay ticks

        a, b = Blocking(), FakeTransport()
        counts = {}

        def run(name, transport, batch):
            try:
                counts[name] = tick(transport, batch=batch)
            finally:
                connection.close()

        ta = threading.Thread(target=run, args=('a', a, 1))
        ta.start()
        self.assertTrue(entered.wait(10))
        tb = threading.Thread(target=run, args=('b', b, 50))
        tb.start()
        tb.join(10)
        self.assertFalse(tb.is_alive(), 'second tick blocked on the locked row instead of skipping it')
        release.set()
        ta.join(10)

        self.assertEqual(a.sent, [1])            # A took the oldest row and held it
        self.assertEqual(sorted(b.sent), [2, 3])  # B skipped it and published the rest
        self.assertEqual(counts, {'a': 1, 'b': 2})
        self.assertEqual(Job.objects.filter(pk__in=[j.pk for j in jobs], status='queued').count(), 3)
