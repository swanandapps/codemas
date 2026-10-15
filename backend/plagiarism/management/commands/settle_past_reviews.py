"""Decide the pending flags on ENDED exams the way the trainer would have after each exam.

Seeded history arrives with every flag pending, as if nobody ever reviewed last month's exams;
Investigation then lists them as work to do. This settles them with one rule:
  - a HIGH-confidence behaviour flag is confirmed when its student is in a code-match pair on
    that exam (two independent kinds of evidence); every other behaviour flag is dismissed;
  - a similarity pair is confirmed when either of its students had a behaviour flag confirmed
    on that exam; every other pair is dismissed.
Each decision goes through the same steps as a trainer's review (reviewed_by, the audit log,
the summary refresh), with the audit entry dated a day after the exam ended so the history
reads as history and students don't get "new decision" badges today. Live and draft exams are
never touched. Dry run unless --yes; running it again finds nothing to decide.

    python manage.py settle_past_reviews          # show the decisions
    python manage.py settle_past_reviews --yes    # make them
"""
from datetime import timedelta

from django.core.management.base import BaseCommand
from django.db import transaction

from exams.models import Exam, exam_status
from plagiarism.models import BehaviouralFlag, PlagiarismFlag, ReviewAuditLog
from plagiarism.views import _log_review, _outcome_changed

CONFIRM_NOTE = ("Reviewed after the exam: your code matched a classmate's and your submission showed "
                "copy signals. Points for this question are withheld.")
# a pair's note reaches BOTH students, including one with no behaviour flag of their own, so it
# states only what is true for both
PAIR_NOTE = "Reviewed after the exam: your code matched a classmate's on this question."



def plan(exam):
    """(behaviour flag, decision) and (pair, decision) for the exam's pending flags."""
    pairs = list(PlagiarismFlag.objects.filter(flagged=True, submission_1__exam=exam)
                 .exclude(review_status='dismissed').select_related('submission_1__student', 'submission_2__student'))
    paired = {s for p in pairs for s in (p.submission_1.student_id, p.submission_2.student_id)}
    behaviour = list(BehaviouralFlag.objects.filter(submission__exam=exam, review_status='pending')
                     .select_related('submission__student'))
    b_plan = [(f, 'confirmed' if f.confidence == 'high' and f.submission.student_id in paired else 'dismissed')
              for f in behaviour]
    confirmed = {f.submission.student_id for f, d in b_plan if d == 'confirmed'} | set(
        BehaviouralFlag.objects.filter(submission__exam=exam, review_status='confirmed')
        .values_list('submission__student_id', flat=True))
    p_plan = [(p, 'confirmed' if {p.submission_1.student_id, p.submission_2.student_id} & confirmed else 'dismissed')
              for p in pairs if p.review_status == 'pending']
    return b_plan, p_plan


class Command(BaseCommand):
    help = "Decide pending flags on ended exams as the trainer would have (dry run unless --yes)."

    def add_arguments(self, parser):
        parser.add_argument('--yes', action='store_true', help='make the decisions (default: show them)')

    def handle(self, *args, yes=False, **options):
        total = 0
        for exam in Exam.objects.select_related('created_by').order_by('start_time', 'id'):
            if exam_status(exam) != 'ended':
                continue
            b_plan, p_plan = plan(exam)
            if not b_plan and not p_plan:
                continue
            total += len(b_plan) + len(p_plan)
            self.stdout.write(f'{exam.title}')
            for f, d in b_plan:
                self.stdout.write(f'  behaviour  {f.submission.student.username:24} {f.confidence:6} -> {d}')
            for p, d in p_plan:
                self.stdout.write(f'  pair       {p.submission_1.student.username} / {p.submission_2.student.username}'
                                  f'  {p.similarity_score * 100:.0f}% -> {d}')
            if yes:
                self._apply(exam, b_plan, p_plan)
        if not total:
            self.stdout.write('Nothing to decide: every flag on an ended exam already has a decision.')
        elif not yes:
            self.stdout.write(f'Dry run: {total} decisions. Add --yes to make them.')
        else:
            self.stdout.write(f'Made {total} decisions.')

    @transaction.atomic
    def _apply(self, exam, b_plan, p_plan):
        trainer = exam.created_by
        when = (exam.end_time or exam.start_time or exam.created_at) + timedelta(days=1)
        log_ids_before = set(ReviewAuditLog.objects.values_list('id', flat=True))
        students = set()
        for flag, decision, kind in [(f, d, 'behavioural') for f, d in b_plan] + [(p, d, 'similarity') for p, d in p_plan]:
            note = '' if decision == 'dismissed' else CONFIRM_NOTE if kind == 'behavioural' else PAIR_NOTE
            flag.review_status, flag.review_note, flag.reviewed_by = decision, note, trainer
            flag.save()
            _log_review(trainer, kind, flag.id, decision, note)
            if kind == 'behavioural':
                students.add(flag.submission.student_id)
            else:
                students |= {flag.submission_1.student_id, flag.submission_2.student_id}
        ReviewAuditLog.objects.exclude(id__in=log_ids_before).update(created_at=when)
        _outcome_changed(sorted(students), exam.id)
