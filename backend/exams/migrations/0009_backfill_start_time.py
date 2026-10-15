from django.db import migrations
from django.db.models import Min


def backfill(apps, schema_editor):
    """Exams opened before going live stamped start_time have none, so dashboards skipped them.
    Use the first submission, or when the exam was created if nobody has submitted yet."""
    Exam = apps.get_model('exams', 'Exam')
    for exam in Exam.objects.filter(start_time__isnull=True).annotate(first_sub=Min('submissions__submitted_at')):
        if exam.is_active or exam.first_sub:
            exam.start_time = min(t for t in (exam.first_sub, exam.created_at) if t)
            exam.save(update_fields=['start_time'])


class Migration(migrations.Migration):
    dependencies = [
        ("exams", "0008_exam_sections"),
    ]

    operations = [
        migrations.RunPython(backfill, migrations.RunPython.noop),
    ]
