from django.db.models import Q
from django.db.models.signals import pre_delete, pre_save
from django.dispatch import receiver
from .models import Exam


@receiver(pre_save, sender=Exam)
def on_exam_status_change(sender, instance, **kwargs):
    """
    Watches every save on the Exam model. When is_active transitions
    from True → False (trainer closes the exam), we queue the batch
    plagiarism check for all questions in that exam.

    Why pre_save and not post_save:
      pre_save lets us compare the old DB value against the new value
      before the write happens. With post_save the instance already has
      the new value so we'd need to query the DB again to get the old one,
      which is an extra round-trip.

    Why not a signal on the PUT endpoint directly:
      Signals are more reliable — they fire regardless of how the exam
      is closed (admin panel, API, management command, future dashboard).
      Putting the trigger in the view would break if someone closes the
      exam via Django admin.
    """
    if not instance.pk:
        return  # this is a brand new exam being created — no previous state to compare

    try:
        previous = Exam.objects.get(pk=instance.pk)
    except Exam.DoesNotExist:
        return

    # only trigger when transitioning active → inactive, not the other way around
    # and not on unrelated field updates (title change, description change etc.)
    if previous.is_active and not instance.is_active:
        from plagiarism.tasks import run_exam_plagiarism_check
        run_exam_plagiarism_check.delay(instance.pk)
        print(f'[SIGNAL] exam "{instance.title}" closed — plagiarism check queued')

    if not previous.is_active and instance.is_active:
        enrolled = instance.enroll_audience()  # going live puts it in front of its sections, no manual step
        print(f'[SIGNAL] exam "{instance.title}" opened — {enrolled} students enrolled')
        from codemas.notifications import notify_exam_open
        notify_exam_open(instance)
        print(f'[SIGNAL] exam "{instance.title}" opened — enrolled students notified')


@receiver(pre_delete, sender=Exam)
def on_exam_delete(sender, instance, **kwargs):
    """Deleting an exam cascades its submissions and flags; this also removes the rows
    that point at those by plain id (no foreign key), so nothing is left behind:
    execution jobs, review-log entries and legacy per-flag disputes (appeals with an exam cascade).
    """
    from jobs.models import Job
    from plagiarism.models import BehaviouralFlag, PlagiarismFlag, ReviewAuditLog
    from submissions.models import Submission
    from support.models import DisputeRequest

    sub_ids = list(Submission.objects.filter(exam=instance).values_list('id', flat=True))
    b_ids = list(BehaviouralFlag.objects.filter(submission_id__in=sub_ids).values_list('id', flat=True))
    p_ids = list(PlagiarismFlag.objects.filter(Q(submission_1_id__in=sub_ids) | Q(submission_2_id__in=sub_ids))
                 .values_list('id', flat=True))
    by_flag = Q(flag_type='behavioural', flag_id__in=b_ids) | Q(flag_type='similarity', flag_id__in=p_ids)
    Job.objects.filter(kind=Job.KIND_EXECUTE, subject_id__in=sub_ids).delete()
    ReviewAuditLog.objects.filter(by_flag).delete()
    DisputeRequest.objects.filter(by_flag).delete()
