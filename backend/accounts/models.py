from django.contrib.auth.models import AbstractUser, UserManager as DjangoUserManager
from django.db import models

# Create your models here.


class UserManager(DjangoUserManager):
    """
    Same as Django's default UserManager, except createsuperuser produces a
    trainer, not a student — the model's role default is 'student', which
    doesn't make sense for an account created via `createsuperuser`.
    """

    def create_superuser(self, username, email=None, password=None, **extra_fields):
        extra_fields.setdefault('role', 'trainer')
        return super().create_superuser(username, email=email, password=password, **extra_fields)


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
    # When the student last opened My results or Disputes: trainer decisions and appeal rulings
    # after this are "new" (sidebar badges, Home banner). None = never looked, everything is new.
    integrity_seen_at = models.DateTimeField(null=True, blank=True)

    objects = UserManager()

    @property
    def score(self) -> int:
        # the canonical points (confirmed plagiarism withheld), so this never disagrees with a page
        from analytics import metrics
        from submissions.models import Submission
        return metrics.points_by_student(Submission.objects.filter(student=self)).get(self.id, 0)

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