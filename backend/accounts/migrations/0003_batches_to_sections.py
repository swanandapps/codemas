"""Rename the seeded batches to sections: Batch-A-2025 -> Section A, and so on.

User.cohort holds the student's section; "cohort" in the product now means all
sections together. Data only, reversible; other values are left alone.
"""
from django.db import migrations

RENAMES = {f'Batch-{s}-2025': f'Section {s}' for s in 'ABCD'}


def forwards(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for old, new in RENAMES.items():
        User.objects.filter(cohort=old).update(cohort=new)


def backwards(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    for old, new in RENAMES.items():
        User.objects.filter(cohort=new).update(cohort=old)


class Migration(migrations.Migration):
    dependencies = [('accounts', '0002_alter_user_managers')]

    operations = [migrations.RunPython(forwards, backwards)]
