"""
Shared test fixture for the metrics module and the cross-endpoint
consistency tests. Kept out of tests*.py so both test modules can import it.

Two cohorts, two exams, each exam taken by one cohort only so a cohort's
"latest exam" numbers on the overview must equal the exam's own numbers.

Exam A (Alpha, ended), questions qa1 + qa2
    a1: qa1 failed, qa1 passed (retry that later passes), qa2 passed
    a2: qa1 failed, qa1 failed, qa2 pending
    a3: qa1 passed (flag, pending review), qa2 error
    a4: enrolled, never submitted
    a5: NOT enrolled, qa1 failed (flag, confirmed)
    a6: qa2 passed
    root: superuser with role student, enrolled, qa1 passed (flag) -> excluded everywhere

    took 5 (a1 a2 a3 a5 a6) / enrolled 5 (a1 a2 a3 a4 a6)       -> 100%
    success: passed = solved at least half of 2 questions = at least 1
             3 passed (a1 a3 a6) / 5 took                       -> 60.0%
             (a3: qa2 is an error, never solved; a6: 1 of 2)
    per question: qa1 2 solved (a1 a3) / 4 attempted            -> 50.0%  (hardest)
                  qa2 2 solved (a1 a6) / 2 attempted            -> 100.0% (a2 pending, a3 error)
    graded submissions 9
    flagged students 2 (a3 a5) / 5 took                         -> 40.0%
    flags to review 1 (a3)

Exam B (Beta, live), questions qb1 + qb2
    b1: qb1 passed (flag, pending review), qb2 failed
    b2: qb1 failed, qb1 failed, qb1 running
    b3: enrolled, never submitted

    took 2 / enrolled 3                                         -> 66.7%
    success 1 passed (b1, 1 of 2) / 2 took                      -> 50.0%
    per question: qb1 1 / 2 -> 50.0%, qb2 0 / 1 -> 0.0% (hardest)
    graded submissions 4
    flagged students 1 / 2                                      -> 50.0%
    flags to review 1 (b1)
"""
from datetime import timedelta
from types import SimpleNamespace

from django.utils import timezone

from accounts.models import User
from exams.models import Exam, ExamEnrollment, Question
from plagiarism.models import BehaviouralFlag
from submissions.models import Submission


EXPECTED = {
    'A': {
        'took': 5, 'enrolled': 5, 'took_rate': 100.0,
        'passed_students': 3, 'accepted_rate': 60.0, 'graded_submissions': 9,
        'flagged_students': 2, 'flagged_students_rate': 40.0,
        'flags_to_review': 1,
    },
    'B': {
        'took': 2, 'enrolled': 3, 'took_rate': 66.7,
        'passed_students': 1, 'accepted_rate': 50.0, 'graded_submissions': 4,
        'flagged_students': 1, 'flagged_students_rate': 50.0,
        'flags_to_review': 1,
    },
}


def _flag(sub, review_status='pending', risk=0.5):
    return BehaviouralFlag.objects.create(
        submission=sub, risk_score=risk, confidence='medium', review_status=review_status,
    )


def build_fixture():
    now = timezone.now()
    trainer = User.objects.create_user(username='trainer', password='pw', role='trainer')

    def student(name, cohort, **extra):
        return User.objects.create_user(username=name, password='pw', role='student', cohort=cohort, **extra)

    a1, a2, a3, a4, a5, a6 = (student(f'a{i}', 'Alpha') for i in range(1, 7))
    root = student('root', 'Alpha', is_superuser=True, is_staff=True)
    b1, b2, b3 = (student(f'b{i}', 'Beta') for i in range(1, 4))

    exam_a = Exam.objects.create(
        title='Exam A', created_by=trainer, duration_minutes=60,
        start_time=now - timedelta(days=10), end_time=now - timedelta(days=10) + timedelta(hours=1),
    )
    exam_b = Exam.objects.create(
        title='Exam B', created_by=trainer, duration_minutes=60, is_active=True,
        start_time=now - timedelta(hours=1), end_time=now + timedelta(days=1),
    )
    qa1 = Question.objects.create(exam=exam_a, title='QA1', description='d', difficulty='easy')
    qa2 = Question.objects.create(exam=exam_a, title='QA2', description='d', difficulty='medium')
    qb1 = Question.objects.create(exam=exam_b, title='QB1', description='d', difficulty='easy')
    qb2 = Question.objects.create(exam=exam_b, title='QB2', description='d', difficulty='hard')

    for s in (a1, a2, a3, a4, a6, root):
        ExamEnrollment.objects.create(exam=exam_a, student=s)
    for s in (b1, b2, b3):
        ExamEnrollment.objects.create(exam=exam_b, student=s)

    attempt = {}

    def sub(stu, exam, q, status):
        key = (stu.id, q.id)
        attempt[key] = attempt.get(key, 0) + 1
        return Submission.objects.create(
            student=stu, exam=exam, question=q, code='x', language='python',
            attempt_number=attempt[key], status=status, time_to_complete_seconds=60,
        )

    sub(a1, exam_a, qa1, 'failed')
    sub(a1, exam_a, qa1, 'passed')
    sub(a1, exam_a, qa2, 'passed')
    sub(a2, exam_a, qa1, 'failed')
    sub(a2, exam_a, qa1, 'failed')
    sub(a2, exam_a, qa2, 'pending')
    _flag(sub(a3, exam_a, qa1, 'passed'), 'pending', risk=0.734)
    sub(a3, exam_a, qa2, 'error')
    _flag(sub(a5, exam_a, qa1, 'failed'), 'confirmed', risk=0.4)
    sub(a6, exam_a, qa2, 'passed')
    _flag(sub(root, exam_a, qa1, 'passed'), 'pending', risk=0.99)

    _flag(sub(b1, exam_b, qb1, 'passed'), 'pending', risk=0.6)
    sub(b1, exam_b, qb2, 'failed')
    sub(b2, exam_b, qb1, 'failed')
    sub(b2, exam_b, qb1, 'failed')
    sub(b2, exam_b, qb1, 'running')

    return SimpleNamespace(
        trainer=trainer, root=root,
        a1=a1, a2=a2, a3=a3, a4=a4, a5=a5, a6=a6, b1=b1, b2=b2, b3=b3,
        exam_a=exam_a, exam_b=exam_b, qa1=qa1, qa2=qa2, qb1=qb1, qb2=qb2,
    )
