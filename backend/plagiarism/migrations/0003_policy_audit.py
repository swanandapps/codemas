from django.conf import settings
from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ('plagiarism', '0002_behaviouralflag'),
        migrations.swappable_dependency(settings.AUTH_USER_MODEL),
    ]

    operations = [
        migrations.CreateModel(
            name='PlagiarismPolicy',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('paste_weight', models.FloatField(default=0.4)),
                ('time_weight', models.FloatField(default=0.3)),
                ('tab_weight', models.FloatField(default=0.15)),
                ('submission_weight', models.FloatField(default=0.15)),
                ('min_risk_score', models.FloatField(default=0.2)),
                ('similarity_threshold', models.FloatField(default=0.8)),
                ('easy_baseline_s', models.IntegerField(default=90)),
                ('medium_baseline_s', models.IntegerField(default=240)),
                ('hard_baseline_s', models.IntegerField(default=480)),
                ('updated_at', models.DateTimeField(auto_now=True)),
                ('updated_by', models.ForeignKey(
                    blank=True, null=True,
                    on_delete=django.db.models.deletion.SET_NULL,
                    related_name='policy_updates',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
        ),
        migrations.CreateModel(
            name='ReviewAuditLog',
            fields=[
                ('id', models.BigAutoField(auto_created=True, primary_key=True, serialize=False, verbose_name='ID')),
                ('flag_type', models.CharField(choices=[('behavioural', 'Behavioural'), ('similarity', 'Similarity')], max_length=20)),
                ('flag_id', models.IntegerField()),
                ('action', models.CharField(max_length=20)),
                ('note', models.TextField(blank=True)),
                ('created_at', models.DateTimeField(auto_now_add=True)),
                ('reviewed_by', models.ForeignKey(
                    on_delete=django.db.models.deletion.CASCADE,
                    related_name='audit_logs',
                    to=settings.AUTH_USER_MODEL,
                )),
            ],
            options={'ordering': ['-created_at']},
        ),
    ]
