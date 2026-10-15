from django.db import models
from django.conf import settings


class DisputeRequest(models.Model):
    """A student's appeal against a plagiarism decision: one round, one per (student, exam).

    The student responds once to a CONFIRMED decision on an exam; a trainer then upholds it
    (no flag changes) or overturns it (the student's own behaviour flags on the exam become
    dismissed, so their points come back; classmates are not affected). A ruling is final.

    Rows filed before appeals were per exam ("legacy") point at a single flag through
    flag_type/flag_id; their exam was backfilled from that flag where it still exists.
    """
    STATUS_CHOICES = [
        ('open',        'Open'),         # waiting for a trainer
        ('upheld',      'Upheld'),       # the decision stands
        ('overturned',  'Overturned'),   # the decision was reversed: points restored
    ]
    FLAG_TYPE_CHOICES = [
        ('behavioural', 'Behavioural'),
        ('similarity',  'Similarity'),
    ]

    student      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='disputes')
    # null only on legacy rows whose flag no longer exists
    exam         = models.ForeignKey('exams.Exam', null=True, blank=True, on_delete=models.CASCADE, related_name='appeals')
    # legacy rows only: the one flag a dispute used to be filed on
    flag_type    = models.CharField(max_length=20, choices=FLAG_TYPE_CHOICES, blank=True, null=True)
    flag_id      = models.IntegerField(null=True, blank=True)
    student_note = models.TextField()
    # the trainer's note(s) on the decision when the appeal was filed: an overturn rewrites the
    # flags' notes, so the original decision is kept here for both sides to read
    decision_note = models.TextField(blank=True)
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='open')

    resolved_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='resolved_disputes',
    )
    resolution_note  = models.TextField(blank=True)
    created_at       = models.DateTimeField(auto_now_add=True)
    resolved_at      = models.DateTimeField(null=True, blank=True)

    class Meta:
        ordering = ['-created_at']
        constraints = [
            # one appeal per student and exam; legacy per-flag rows (flag_id set) are exempt
            models.UniqueConstraint(fields=['student', 'exam'], condition=models.Q(flag_id__isnull=True),
                                    name='one_appeal_per_student_exam'),
        ]

    def __str__(self):
        return f'Appeal #{self.id} by {self.student.username} (exam {self.exam_id}, {self.status})'
