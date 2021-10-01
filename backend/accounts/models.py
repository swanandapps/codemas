from django.contrib.auth.models import AbstractUser
from django.db import models

# Create your models here.

# AbstractUser - django full user model as base class, inherit and add on top
# role choices restricts role coloum to 3 roles
class User(AbstractUser):
    ROLE_CHOICES = [

        ('student','Student'),
        ('trainer', 'Trainer'),
        ('admin', 'Admin')
    ]

    role = models.CharField(max_length=10, choices=ROLE_CHOICES, default='student')
    cohort = models.CharField(max_length=100, blank=True)

    @property
    def score(self) -> int:
        from submissions.models import Submission
        passed = Submission.objects.filter(student=self, status='passed').select_related('question')
        # one point per unique question passed, scaled by difficulty
        seen = set()
        total = 0
        for sub in passed:
            if sub.question_id not in seen:
                seen.add(sub.question_id)
                total += sub.question.points
        return total

    @property
    def current_streak(self) -> int:
        from submissions.models import Submission
        from django.utils import timezone
        from datetime import timedelta
        dates = (
            Submission.objects
            .filter(student=self)
            .values_list('submitted_at__date', flat=True)
            .distinct()
            .order_by('-submitted_at__date')
        )
        streak = 0
        today = timezone.now().date()
        for i, d in enumerate(dates):
            expected = today - timedelta(days=i)
            if d == expected:
                streak += 1
            else:
                break
        return streak

    def __str__(self):
        return f"{self.username} ({self.role})"