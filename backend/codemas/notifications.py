from django.core.mail import send_mail
from django.conf import settings


def _send(subject: str, body: str, to: list[str]) -> None:
    send_mail(
        subject=subject,
        message=body,
        from_email=settings.DEFAULT_FROM_EMAIL,
        recipient_list=to,
        fail_silently=True,  # never crash the main flow for an email
    )


def notify_exam_open(exam) -> None:
    from exams.models import ExamEnrollment
    emails = list(
        ExamEnrollment.objects
        .filter(exam=exam)
        .select_related('student')
        .values_list('student__email', flat=True)
    )
    if not emails:
        return
    _send(
        subject=f'[CodeMas] Exam now open: {exam.title}',
        body=(
            f'Hi,\n\n'
            f'The exam "{exam.title}" is now open.\n'
            f'Duration: {exam.duration_minutes} minutes.\n\n'
            f'Log in at http://localhost:5173/exams to start.\n\n'
            f'Good luck!'
        ),
        to=emails,
    )


def notify_result_ready(submission) -> None:
    email = submission.student.email
    if not email:
        return
    status_text = 'passed ✓' if submission.status == 'passed' else 'failed ✗'
    _send(
        subject=f'[CodeMas] Result: {submission.question.title} — {submission.status}',
        body=(
            f'Hi {submission.student.username},\n\n'
            f'Your attempt #{submission.attempt_number} for '
            f'"{submission.question.title}" has {status_text}.\n\n'
            f'View your results at http://localhost:5173/results'
        ),
        to=[email],
    )


def notify_plagiarism_flagged(flag) -> None:
    from django.contrib.auth import get_user_model
    User = get_user_model()
    trainers = User.objects.filter(role='trainer').values_list('email', flat=True)
    emails = [e for e in trainers if e]
    if not emails:
        return
    _send(
        subject='[CodeMas] New plagiarism flag requires review',
        body=(
            f'A new plagiarism flag has been created.\n\n'
            f'Students: {flag.submission_1.student.username} vs {flag.submission_2.student.username}\n'
            f'Similarity: {flag.similarity_score * 100:.1f}%\n\n'
            f'Review at http://localhost:5173/dashboard/plagiarism'
        ),
        to=list(emails),
    )
