import uuid
from datetime import timedelta

from django.conf import settings
from django.db import transaction
from django.utils import timezone

from .models import MAX_ATTEMPTS, Job


def _require_atomic(in_atomic=None):
    if in_atomic is None:
        in_atomic = transaction.get_connection().in_atomic_block
    if not in_atomic:
        raise RuntimeError('enqueue() must be called inside transaction.atomic() with the row it belongs to')


def enqueue(kind, subject_id):
    """Write the outbox row. Never publishes; the relay does that after commit."""
    _require_atomic()
    return Job.objects.create(kind=kind, subject_id=subject_id)


# ── Lease protocol (claim / complete / fail) ──────────────────────────────────

class JobDone(Exception): pass
class JobBusy(Exception): pass
class JobGone(Exception): pass
class JobDead(Exception): pass
class StaleLease(Exception): pass


def _subject(job):
    from submissions.models import Submission
    return Submission.objects.select_related('question').filter(pk=job.subject_id).first()


def claim(job_id):
    """Take the lease. One locked read decides every outcome, so two claims can't both win.
    Refusals are raised after the transaction commits: raising inside it would roll back the
    'gone'/'dead' bookkeeping written on the way out."""
    with transaction.atomic():
        job, subject, refusal = _claim_locked(job_id)
    if refusal:
        raise refusal
    return job, subject


def _claim_locked(job_id):
    job = Job.objects.select_for_update().get(pk=job_id)  # DoesNotExist → 404 in the view
    now = timezone.now()
    if job.status in Job.TERMINAL:
        return job, None, JobDone
    if job.status == 'running' and job.lease_expires_at and job.lease_expires_at > now:
        return job, None, JobBusy
    subject = _subject(job)
    if subject is None:
        job.status, job.finished_at, job.last_error = 'failed', now, 'subject deleted'
        job.save()
        return job, None, JobGone
    if job.attempt >= MAX_ATTEMPTS:
        job.status, job.finished_at = 'dead', now
        job.save()
        subject.status = 'error'
        subject.save(update_fields=['status'])
        return job, subject, JobDead
    job.status = 'running'
    job.attempt += 1
    job.lease_token = uuid.uuid4()
    job.lease_expires_at = now + timedelta(seconds=settings.JOB_LEASE_SECONDS)
    job.started_at = job.started_at or now
    job.save()
    subject.status = 'running'
    subject.save(update_fields=['status'])
    return job, subject, None


@transaction.atomic
def complete(job_id, lease_token, results):
    from .execute import apply_result
    job = Job.objects.select_for_update().get(pk=job_id)
    if job.status != 'running' or str(job.lease_token) != str(lease_token):
        raise StaleLease
    subject = _subject(job)
    submission_status = apply_result(subject, results) if subject else 'gone'
    job.status, job.finished_at, job.lease_token, job.lease_expires_at = 'succeeded', timezone.now(), None, None
    job.save()
    return job, submission_status


@transaction.atomic
def fail(job_id, lease_token, error):
    """The handler gave up (infrastructure problem). Release the lease and put the job back in the
    outbox, so the relay republishes it on its next tick in either transport. The attempt still counts."""
    job = Job.objects.select_for_update().get(pk=job_id)
    if job.status != 'running' or str(job.lease_token) != str(lease_token):
        raise StaleLease
    job.status, job.lease_token, job.lease_expires_at = 'pending', None, None
    job.last_error = (error or '')[:2000]
    job.save()
    return job
