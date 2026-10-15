"""Read-only demo_* views: the data an interviewer asks to see, browsable in the database tool
(Railway's Data tab) without writing SQL live.

Facts only, joined into readable rows: names instead of ids, counts that need no app rule.
App metrics (success rate, withheld points, ranks) are NOT recomputed here; they follow rules in
analytics/metrics.py, and a second copy in SQL could disagree with the pages.
"""
from django.db import migrations

NAME = "NULLIF(TRIM(u.first_name || ' ' || u.last_name), '')"

VIEWS = {
    'demo_accounts': f"""
        SELECT u.username, {NAME} AS full_name, u.role, NULLIF(u.cohort, '') AS section, u.email,
               u.is_active, u.date_joined, u.last_login
        FROM accounts_user u
        ORDER BY u.date_joined DESC, u.id DESC""",

    # students as the app counts them: role student, never a superuser
    'demo_students': f"""
        SELECT u.username, {NAME} AS full_name, NULLIF(u.cohort, '') AS section,
               (SELECT COUNT(DISTINCT s.exam_id) FROM submissions_submission s WHERE s.student_id = u.id) AS exams_taken,
               (SELECT COUNT(*) FROM submissions_submission s WHERE s.student_id = u.id) AS submissions,
               (SELECT COUNT(*) FROM submissions_submission s WHERE s.student_id = u.id AND s.status = 'passed') AS passed_submissions,
               (SELECT COUNT(*) FROM plagiarism_behaviouralflag f JOIN submissions_submission s ON s.id = f.submission_id
                 WHERE s.student_id = u.id AND f.review_status <> 'dismissed') AS behaviour_flags,
               (SELECT COUNT(*) FROM plagiarism_behaviouralflag f JOIN submissions_submission s ON s.id = f.submission_id
                 WHERE s.student_id = u.id AND f.review_status = 'confirmed')
             + (SELECT COUNT(*) FROM plagiarism_plagiarismflag p
                 JOIN submissions_submission s1 ON s1.id = p.submission_1_id
                 JOIN submissions_submission s2 ON s2.id = p.submission_2_id
                 WHERE p.flagged AND p.review_status = 'confirmed' AND u.id IN (s1.student_id, s2.student_id)) AS confirmed_flags,
               (SELECT COUNT(*) FROM support_disputerequest d WHERE d.student_id = u.id AND d.status = 'open') AS open_appeals
        FROM accounts_user u
        WHERE u.role = 'student' AND NOT u.is_superuser
        ORDER BY u.username""",

    # status: the same rule as exams.models.exam_status
    'demo_exams': """
        SELECT e.id AS exam_id, e.title,
               CASE WHEN e.end_time IS NOT NULL AND e.end_time <= now() THEN 'ended'
                    WHEN e.is_active THEN 'live' ELSE 'draft' END AS status,
               e.start_time, e.end_time, e.duration_minutes,
               (SELECT COUNT(*) FROM exams_question q WHERE q.exam_id = e.id) AS questions,
               (SELECT COUNT(*) FROM exams_examenrollment en WHERE en.exam_id = e.id) AS enrolled,
               (SELECT COUNT(DISTINCT s.student_id) FROM submissions_submission s WHERE s.exam_id = e.id) AS students_submitted,
               (SELECT COUNT(*) FROM submissions_submission s WHERE s.exam_id = e.id) AS submissions,
               c.username AS created_by
        FROM exams_exam e JOIN accounts_user c ON c.id = e.created_by_id
        ORDER BY COALESCE(e.start_time, e.created_at) DESC, e.id DESC""",

    'demo_submissions': """
        SELECT s.id AS submission_id, s.submitted_at, e.title AS exam, q.title AS question, u.username AS student,
               s.attempt_number AS attempt, s.language, s.status, s.time_to_complete_seconds AS seconds_to_solve,
               s.paste_char_count AS paste_chars, s.tab_switch_count AS tab_switches
        FROM submissions_submission s
        JOIN exams_exam e ON e.id = s.exam_id
        JOIN exams_question q ON q.id = s.question_id
        JOIN accounts_user u ON u.id = s.student_id
        ORDER BY s.submitted_at DESC, s.id DESC""",

    # risk on the 0-100 scale the pages show ("Risk 70")
    'demo_behaviour_flags': """
        SELECT f.id AS flag_id, f.created_at, e.title AS exam, q.title AS question, u.username AS student,
               s.attempt_number AS attempt, f.confidence, ROUND((f.risk_score * 100)::numeric) AS risk_score,
               f.signals_triggered::text AS signals, f.review_status, NULLIF(f.review_note, '') AS review_note,
               r.username AS reviewed_by
        FROM plagiarism_behaviouralflag f
        JOIN submissions_submission s ON s.id = f.submission_id
        JOIN exams_exam e ON e.id = s.exam_id
        JOIN exams_question q ON q.id = s.question_id
        JOIN accounts_user u ON u.id = s.student_id
        LEFT JOIN accounts_user r ON r.id = f.reviewed_by_id
        ORDER BY f.created_at DESC, f.id DESC""",

    # only pairs above the policy threshold (flagged), as the case file shows them
    'demo_similarity_pairs': """
        SELECT p.id AS flag_id, p.checked_at, e.title AS exam, q.title AS question,
               u1.username AS student_1, u2.username AS student_2,
               ROUND((p.similarity_score * 100)::numeric, 1) AS similarity_pct,
               p.review_status, NULLIF(p.review_note, '') AS review_note, r.username AS reviewed_by
        FROM plagiarism_plagiarismflag p
        JOIN submissions_submission s1 ON s1.id = p.submission_1_id
        JOIN submissions_submission s2 ON s2.id = p.submission_2_id
        JOIN exams_exam e ON e.id = s1.exam_id
        JOIN exams_question q ON q.id = s1.question_id
        JOIN accounts_user u1 ON u1.id = s1.student_id
        JOIN accounts_user u2 ON u2.id = s2.student_id
        LEFT JOIN accounts_user r ON r.id = p.reviewed_by_id
        WHERE p.flagged
        ORDER BY p.checked_at DESC, p.id DESC""",

    'demo_review_log': """
        SELECT l.created_at AS logged_at, r.username AS trainer, l.action, l.flag_type, l.flag_id,
               NULLIF(l.note, '') AS note
        FROM plagiarism_reviewauditlog l
        LEFT JOIN accounts_user r ON r.id = l.reviewed_by_id
        ORDER BY l.created_at DESC, l.id DESC""",

    'demo_appeals': """
        SELECT d.id AS appeal_id, d.created_at AS filed_at, u.username AS student, e.title AS exam, d.status,
               d.student_note, NULLIF(d.decision_note, '') AS decision_note,
               NULLIF(d.resolution_note, '') AS trainer_reply, r.username AS ruled_by, d.resolved_at AS ruled_at
        FROM support_disputerequest d
        JOIN accounts_user u ON u.id = d.student_id
        LEFT JOIN exams_exam e ON e.id = d.exam_id
        LEFT JOIN accounts_user r ON r.id = d.resolved_by_id
        ORDER BY d.created_at DESC, d.id DESC""",
}


class Migration(migrations.Migration):
    dependencies = [
        ('accounts', '0004_user_integrity_seen_at'),
        ('exams', '0009_backfill_start_time'),
        ('submissions', '0008_submission_unique_attempt_per_question'),
        ('plagiarism', '0007_policy_compare_min_risk'),
        ('support', '0002_appeals_per_exam'),
    ]

    operations = [
        migrations.RunSQL(f'CREATE OR REPLACE VIEW {name} AS {sql};', f'DROP VIEW IF EXISTS {name};')
        for name, sql in VIEWS.items()
    ]
