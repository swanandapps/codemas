import uuid

from django.db import models
from django.db.models import Q

MAX_ATTEMPTS = 3


class Job(models.Model):
    """One unit of background work: the transactional outbox row plus its execution lease.

    pending   committed, not yet published (the outbox)
    queued    the transport accepted it
    running   a handler holds a live lease
    succeeded / failed   terminal; failed = the job finished but produced a failure result
    dead      infrastructure failed MAX_ATTEMPTS times
    """
    KIND_EXECUTE = 'execute_submission'
    KINDS = [(KIND_EXECUTE, 'Execute submission')]
    STATUSES = [(s, s) for s in ('pending', 'queued', 'running', 'succeeded', 'failed', 'dead')]
    ACTIVE = ('pending', 'queued', 'running')
    TERMINAL = ('succeeded', 'failed', 'dead')

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    kind = models.CharField(max_length=40, choices=KINDS)
    subject_id = models.PositiveIntegerField()  # submission id for execute_submission
    status = models.CharField(max_length=12, choices=STATUSES, default='pending')
    attempt = models.PositiveSmallIntegerField(default=0)
    lease_token = models.UUIDField(null=True, blank=True)
    lease_expires_at = models.DateTimeField(null=True, blank=True)
    published_at = models.DateTimeField(null=True, blank=True)
    started_at = models.DateTimeField(null=True, blank=True)
    finished_at = models.DateTimeField(null=True, blank=True)
    last_error = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ['-created_at']
        indexes = [
            models.Index(fields=['status', 'created_at']),
            # the status poll (submissions/views.py): filter(kind=, subject_id=). The partial unique
            # index below can't serve it because the poll has no status predicate.
            models.Index(fields=['subject_id', 'kind'], name='jobs_job_subject_idx'),
        ]
        constraints = [
            models.UniqueConstraint(
                fields=['kind', 'subject_id'],
                condition=Q(status__in=('pending', 'queued', 'running')),
                name='one_active_job_per_subject',
            ),
        ]

    def __str__(self):
        return f'{self.kind} #{self.subject_id} [{self.status}]'
