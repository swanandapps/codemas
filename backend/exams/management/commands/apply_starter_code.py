"""Fill in the open demo exam's starter code on questions that have none yet.

seed_data already does this for a fresh seed; run it once on data seeded before
starter code existed. Matches questions by title (exams/starter_code.py
DEMO_STARTERS) and never overwrites a starter a trainer has set.

    python manage.py apply_starter_code
"""
from django.core.management.base import BaseCommand
from django.db.models import Q

from exams.models import Question
from exams.starter_code import DEMO_STARTERS


class Command(BaseCommand):
    help = "Set the demo exam questions' starter code where it is empty."

    def handle(self, *args, **options):
        updated = 0
        for title, starter in DEMO_STARTERS.items():
            updated += Question.objects.filter(title=title).filter(
                Q(starter_code_javascript='') & Q(starter_code_python='')
            ).update(starter_code_javascript=starter['javascript'], starter_code_python=starter['python'])
        self.stdout.write(self.style.SUCCESS(f'Starter code set on {updated} questions.'))
