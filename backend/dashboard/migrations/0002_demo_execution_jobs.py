"""demo_execution_jobs: the code-execution pipeline's history, one row per job.

SQS deletes a message once the Lambda grades it, so the queue keeps no history; the jobs_job
outbox row is the full record (created → sent to the queue → started → finished, or the error).
"""
from django.db import migrations

SQL = """
CREATE OR REPLACE VIEW demo_execution_jobs AS
SELECT j.id AS job_id, j.created_at, j.status, j.attempt AS tries,
       u.username AS student, e.title AS exam, q.title AS question, s.language, s.status AS result,
       j.published_at AS sent_to_queue_at, j.started_at, j.finished_at,
       ROUND(EXTRACT(EPOCH FROM (j.started_at - j.published_at))::numeric, 1) AS seconds_waiting,
       ROUND(EXTRACT(EPOCH FROM (j.finished_at - j.started_at))::numeric, 1) AS seconds_running,
       NULLIF(j.last_error, '') AS error
FROM jobs_job j
LEFT JOIN submissions_submission s ON s.id = j.subject_id AND j.kind = 'execute_submission'
LEFT JOIN accounts_user u ON u.id = s.student_id
LEFT JOIN exams_exam e ON e.id = s.exam_id
LEFT JOIN exams_question q ON q.id = s.question_id
ORDER BY j.created_at DESC;
"""


class Migration(migrations.Migration):
    dependencies = [
        ('dashboard', '0001_demo_views'),
        ('jobs', '0002_job_subject_index'),
    ]

    operations = [migrations.RunSQL(SQL, 'DROP VIEW IF EXISTS demo_execution_jobs;')]
