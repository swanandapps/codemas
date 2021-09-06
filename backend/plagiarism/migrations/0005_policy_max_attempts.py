from django.db import migrations, models


class Migration(migrations.Migration):
    dependencies = [
        ("plagiarism", "0004_policy_version"),
    ]

    operations = [
        migrations.AddField(
            model_name="plagiarismpolicy",
            name="max_attempts",
            field=models.PositiveIntegerField(default=3),
        ),
    ]
