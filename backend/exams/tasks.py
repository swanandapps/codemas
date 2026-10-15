from celery import shared_task
from django.utils import timezone


@shared_task
def auto_manage_exams():
    """
    Runs every minute via Celery beat. Two jobs:

    1. Auto-open: if start_time has passed and exam is still inactive, activate it.
    2. Auto-close: if end_time has passed and exam is still active, deactivate it.

    Deactivating triggers the pre_save signal on Exam which queues the
    plagiarism batch check — so auto-close and manual close behave identically.
    """
    from django.db.models import Q
    from .models import Exam

    now = timezone.now()

    # auto-open exams whose start_time has arrived (no end_time = open until closed)
    to_open = Exam.objects.filter(Q(end_time__isnull=True) | Q(end_time__gt=now),
                                  is_active=False, start_time__lte=now)
    for exam in to_open:
        exam.is_active = True
        exam.save()
        print(f'[SCHEDULER] auto-opened exam: {exam.title}')

    # auto-close exams whose end_time has passed
    to_close = Exam.objects.filter(is_active=True, end_time__lte=now)
    for exam in to_close:
        exam.is_active = False
        exam.save()  # pre_save signal fires here → plagiarism batch queued
        print(f'[SCHEDULER] auto-closed exam: {exam.title}')
