"""Queue the rubric review (and, for failed attempts, the hint) for every graded
submission that does not have one yet.

Live submissions get these from `after_grading` a few seconds after the result.
The demo seed writes submissions and results straight to the database, so that
hook never fires for them; this runs the same tasks over that history. Safe to
re-run: both tasks skip a submission that already has its row.

Run it after every seed (on the backend service; the worker does the calls).
"""
from django.core.management.base import BaseCommand

from ai.models import AIHint, RubricScore
from ai.tasks import generate_hint, score_rubric
from submissions.models import Submission


class Command(BaseCommand):
    help = 'Queue rubric reviews and hints for graded submissions that are missing them.'

    def add_arguments(self, parser):
        parser.add_argument('--sync', action='store_true',
                            help='Run the calls here, one by one, instead of queueing them on the worker.')

    def handle(self, *args, **options):
        graded = Submission.objects.filter(status__in=('passed', 'failed', 'error')).order_by('id')
        has_rubric = RubricScore.objects.values('submission_id')
        has_hint = AIHint.objects.values('submission_id')
        rubric_ids = list(graded.exclude(id__in=has_rubric).values_list('id', flat=True))
        hint_ids = list(graded.filter(status='failed').exclude(id__in=has_hint).values_list('id', flat=True))

        for sub_id in rubric_ids:
            score_rubric(sub_id) if options['sync'] else score_rubric.delay(sub_id)
        for sub_id in hint_ids:
            generate_hint(sub_id) if options['sync'] else generate_hint.delay(sub_id)

        verb = 'Ran' if options['sync'] else 'Queued'
        self.stdout.write(self.style.SUCCESS(
            f'{verb} {len(rubric_ids)} rubric reviews and {len(hint_ids)} hints '
            f'({graded.count()} graded submissions).'
        ))
