"""Write this week's recommendation for every student with a graded exam, now.

Used once after deploy (and after a re-seed) so the demo shows a recommendation
before the first Monday run. Safe to re-run: existing rows for the week are kept.
"""
from django.core.management.base import BaseCommand

from ai.tasks import (
    current_week_start, generate_weekly_recommendation, weekly_recommendation_students,
)


class Command(BaseCommand):
    help = "Generate this week's weekly recommendation for every student with a graded exam."

    def handle(self, *args, **options):
        week_start = current_week_start()
        students = list(weekly_recommendation_students().values_list('id', 'username'))
        made = 0
        for student_id, username in students:
            if generate_weekly_recommendation(student_id, week_start):
                made += 1
            else:
                self.stdout.write(f'  no recommendation for {username}')
        self.stdout.write(self.style.SUCCESS(
            f'{made} of {len(students)} students have a recommendation for the week of {week_start}'
        ))
