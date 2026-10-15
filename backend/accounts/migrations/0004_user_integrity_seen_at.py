"""Add User.integrity_seen_at: when the student last opened My results or Disputes.

Existing accounts are marked as having seen everything now, so decisions made before this
release don't all light up as new at once; accounts created later start at None (never looked).
Reversible: the field is dropped.
"""
from django.db import migrations, models
from django.utils import timezone


def mark_existing_seen(apps, schema_editor):
    User = apps.get_model('accounts', 'User')
    n = User.objects.filter(integrity_seen_at__isnull=True).update(integrity_seen_at=timezone.now())
    print(f'\n  integrity_seen_at set to now on {n} existing account(s)')


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0003_batches_to_sections'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='integrity_seen_at',
            field=models.DateTimeField(blank=True, null=True),
        ),
        migrations.RunPython(mark_existing_seen, migrations.RunPython.noop),
    ]
