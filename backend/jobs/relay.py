"""The outbox relay: moves committed jobs (status 'pending') onto the transport, and sweeps up jobs
whose message or handler got lost. Claiming is idempotent, so publishing a job twice is harmless;
never publishing it is not."""
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.db.models import Q
from django.utils import timezone

from .models import MAX_ATTEMPTS, Job

# A queued job nobody has claimed for this long had its message lost: publish it again.
# Local: nothing else would ever redeliver it.
LOCAL_QUEUED_TOO_LONG = timedelta(minutes=10)
# SQS: wait out the queue's own redelivery (maxReceiveCount 3 x 540 s visibility = 27 min) first.
SQS_QUEUED_TOO_LONG = timedelta(minutes=30)
# SQS: a running job whose lease expired this long ago below MAX_ATTEMPTS is no longer being redelivered.
# Deliveries that never claimed (409 busy, Django unreachable) don't spend attempts, so its message can
# have gone to the DLQ with attempts to spare. Same reasoning as above: longer than SQS's own retries.
SQS_EXPIRED_LEASE_BACKSTOP = timedelta(minutes=30)

ERROR_MAX = 2000


def note_error(previous, note):
    """last_error policy: keep what is already there (usually the handler's own error, the most useful
    line for a human) and add relay/sweep notes after it, one per line. A note of the same kind as the
    last line replaces it, so a queue outage doesn't grow the field every tick. Over ERROR_MAX the
    older text is cut, never the new note."""
    previous = previous or ''
    head, _, last = previous.rpartition('\n')
    kind = note.split(':', 1)[0] + ':'
    if last.startswith(kind):
        previous = head
    text = f'{previous}\n{note}' if previous else note
    if len(text) > ERROR_MAX:
        note = note[:ERROR_MAX]
        text = (previous[:ERROR_MAX - len(note) - 1] + '\n' + note) if len(note) < ERROR_MAX else note
    return text


def tick(transport, batch=50):
    """Publish pending jobs, oldest first. SKIP LOCKED lets several relays run without taking the same rows.
    A job is marked queued only if the transport accepted it; anything else stays pending for the next tick."""
    published = 0
    with transaction.atomic():
        jobs = list(Job.objects.select_for_update(skip_locked=True)
                    .filter(status='pending').order_by('created_at')[:batch])
        if not jobs:
            return 0
        try:
            outcome = transport.publish_many(jobs)
        except Exception as e:  # a transport bug: nothing is known to be sent
            outcome = {str(j.id): repr(e) for j in jobs}
        now = timezone.now()
        for job in jobs:
            error = outcome.get(str(job.id), 'transport returned no result')
            if error is None:
                Job.objects.filter(pk=job.pk).update(status='queued', published_at=now)
                published += 1
            else:
                Job.objects.filter(pk=job.pk).update(last_error=note_error(job.last_error, f'publish failed: {error}'))
    return published


def sweep_stuck(now=None):
    """Safety net for lost messages and crashed handlers. Transport-aware, so the database and the
    SQS dead-letter queue agree on what is dead.

    running, lease expired (or missing):
        attempt >= MAX_ATTEMPTS  -> dead; the submission becomes 'error' (doesn't count as an attempt)
        local                    -> back to pending (nothing else would retry it)
        sqs                      -> left alone: SQS redelivers after the visibility timeout and claim
                                    accepts an expired lease; once expired longer than
                                    SQS_EXPIRED_LEASE_BACKSTOP, back to pending (the backstop)
    queued longer than LOCAL_/SQS_QUEUED_TOO_LONG (or never stamped) -> back to pending.
        A queued job already at MAX_ATTEMPTS is killed by its next claim, which also marks the submission.
    """
    from submissions.models import Submission
    now = now or timezone.now()
    sqs = settings.JOB_TRANSPORT == 'sqs'
    queued_too_long = SQS_QUEUED_TOO_LONG if sqs else LOCAL_QUEUED_TOO_LONG
    requeued = dead = 0
    with transaction.atomic():
        expired = Job.objects.select_for_update(skip_locked=True).filter(status='running').filter(
            Q(lease_expires_at__lt=now) | Q(lease_expires_at__isnull=True))
        if sqs:
            expired = expired.filter(Q(attempt__gte=MAX_ATTEMPTS) | Q(lease_expires_at__isnull=True)
                                     | Q(lease_expires_at__lt=now - SQS_EXPIRED_LEASE_BACKSTOP))
        for job in list(expired):
            if job.attempt >= MAX_ATTEMPTS:
                Job.objects.filter(pk=job.pk).update(
                    status='dead', finished_at=now, lease_token=None, lease_expires_at=None,
                    last_error=note_error(job.last_error,
                                          f'sweep: lease expired at max attempts ({job.attempt}/{MAX_ATTEMPTS}); dead'))
                Submission.objects.filter(pk=job.subject_id).update(status='error')
                dead += 1
            else:
                note = (f'sweep: lease expired {int(SQS_EXPIRED_LEASE_BACKSTOP.total_seconds() // 60)}+ min ago; '
                        'requeued by sweep backstop' if sqs
                        else f'sweep: lease expired on attempt {job.attempt}; requeued')
                Job.objects.filter(pk=job.pk).update(status='pending', lease_token=None, lease_expires_at=None,
                                                     last_error=note_error(job.last_error, note))
                requeued += 1
        stale = list(Job.objects.select_for_update(skip_locked=True).filter(status='queued').filter(
            Q(published_at__lt=now - queued_too_long) | Q(published_at__isnull=True)))
        minutes = int(queued_too_long.total_seconds() // 60)
        for job in stale:
            Job.objects.filter(pk=job.pk).update(
                status='pending',
                last_error=note_error(job.last_error, f'sweep: queued {minutes} min with no claim; requeued'))
            requeued += 1
    return {'requeued': requeued, 'dead': dead}
