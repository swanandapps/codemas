"""Disputes become one-round appeals per (student, exam).

Schema: add exam (nullable) and decision_note; flag_type/flag_id become nullable (kept for
legacy display); statuses become open / upheld / overturned; one appeal per student and exam
for new appeals (legacy per-flag rows are exempt, a student may have several on one exam).

Data, on existing rows:
    resolved  -> upheld   (the trainer closed it; no flag was ever changed by a dispute)
    escalated -> open     (it was never decided, so it goes back in the queue)
    exam      <- the exam of the flag it was filed on, where that flag still exists
    decision_note <- that flag's review note
Reverse maps upheld/overturned back to resolved (escalated can't be told apart from open, so
it stays open); the schema reverse needs every row to still have a flag_type/flag_id.
"""
import django.db.models.deletion
from django.db import migrations, models


def migrate_appeals(apps):
    """The data step, separate from the schema so a test can run it. Returns the counts."""
    DisputeRequest = apps.get_model('support', 'DisputeRequest')
    BehaviouralFlag = apps.get_model('plagiarism', 'BehaviouralFlag')
    PlagiarismFlag = apps.get_model('plagiarism', 'PlagiarismFlag')

    counts = {
        'resolved_to_upheld': DisputeRequest.objects.filter(status='resolved').update(status='upheld'),
        'escalated_to_open': DisputeRequest.objects.filter(status='escalated').update(status='open'),
        'exam_backfilled': 0,
        'exam_unresolved': 0,
    }
    for d in DisputeRequest.objects.filter(exam__isnull=True, flag_id__isnull=False):
        if d.flag_type == 'behavioural':
            flag = BehaviouralFlag.objects.filter(pk=d.flag_id).select_related('submission').first()
            exam_id = flag.submission.exam_id if flag else None
        else:
            flag = PlagiarismFlag.objects.filter(pk=d.flag_id).select_related('submission_1').first()
            exam_id = flag.submission_1.exam_id if flag else None
        if exam_id is None:
            counts['exam_unresolved'] += 1
            continue
        d.exam_id = exam_id
        d.decision_note = d.decision_note or flag.review_note
        d.save(update_fields=['exam', 'decision_note'])
        counts['exam_backfilled'] += 1
    return counts


def unmigrate_appeals(apps):
    DisputeRequest = apps.get_model('support', 'DisputeRequest')
    DisputeRequest.objects.filter(status__in=('upheld', 'overturned')).update(status='resolved')


def forwards(apps, schema_editor):
    counts = migrate_appeals(apps)
    print('\n  appeals: ' + ', '.join(f'{k.replace("_", " ")} {v}' for k, v in counts.items()))


def backwards(apps, schema_editor):
    unmigrate_appeals(apps)


class Migration(migrations.Migration):

    dependencies = [
        ('support', '0001_initial'),
        ('exams', '0001_initial'),
        ('plagiarism', '0007_policy_compare_min_risk'),
    ]

    operations = [
        migrations.AddField(
            model_name='disputerequest',
            name='exam',
            field=models.ForeignKey(blank=True, null=True, on_delete=django.db.models.deletion.CASCADE,
                                    related_name='appeals', to='exams.exam'),
        ),
        migrations.AddField(
            model_name='disputerequest',
            name='decision_note',
            field=models.TextField(blank=True),
        ),
        migrations.AlterField(
            model_name='disputerequest',
            name='flag_type',
            field=models.CharField(blank=True, choices=[('behavioural', 'Behavioural'), ('similarity', 'Similarity')],
                                   max_length=20, null=True),
        ),
        migrations.AlterField(
            model_name='disputerequest',
            name='flag_id',
            field=models.IntegerField(blank=True, null=True),
        ),
        migrations.AlterField(
            model_name='disputerequest',
            name='status',
            field=models.CharField(choices=[('open', 'Open'), ('upheld', 'Upheld'), ('overturned', 'Overturned')],
                                   default='open', max_length=20),
        ),
        # legacy rows all have a flag_id, so the constraint holds before the data step; the
        # data step runs last (Postgres won't alter a table with pending row updates in the same transaction)
        migrations.AddConstraint(
            model_name='disputerequest',
            constraint=models.UniqueConstraint(condition=models.Q(('flag_id__isnull', True)),
                                               fields=('student', 'exam'), name='one_appeal_per_student_exam'),
        ),
        migrations.RunPython(forwards, backwards),
    ]
