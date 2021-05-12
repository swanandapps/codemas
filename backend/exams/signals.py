from django.db.models.signals import pre_save
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
        from codemas.notifications import notify_exam_open
        notify_exam_open(instance)
        print(f'[SIGNAL] exam "{instance.title}" opened — enrolled students notified')
