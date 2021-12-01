from django.db import models
from django.conf import settings


class DisputeRequest(models.Model):
    STATUS_CHOICES = [
        ('open',       'Open'),
        ('resolved',   'Resolved'),
        ('escalated',  'Escalated'),
    ]
    FLAG_TYPE_CHOICES = [
        ('behavioural', 'Behavioural'),
        ('similarity',  'Similarity'),
    ]

    student      = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='disputes')
    flag_type    = models.CharField(max_length=20, choices=FLAG_TYPE_CHOICES)
    flag_id      = models.IntegerField()
    student_note = models.TextField()
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

    def __str__(self):
        return f'Dispute #{self.id} by {self.student.username} ({self.flag_type} flag {self.flag_id})'
