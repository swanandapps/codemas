from django.db import models  # base module for all Django model fields
from django.conf import settings  # lets us reference AUTH_USER_MODEL without importing User directly


def newest_exam_first(path=''):
    """order_by term: the exam that ran most recently first. A draft never opened has no
    start_time, so it sorts by when it was made. path reaches the exam, e.g. 'submission__exam__'."""
    from django.db.models.functions import Coalesce
    return Coalesce(f'{path}start_time', f'{path}created_at').desc()


def exam_status(exam, now=None):
    """'draft', 'live' or 'ended', the same on every page. Ended = its end time has passed;
    live = open (is_active) and not past its end time, with or without an end time; else draft."""
    from django.utils import timezone
    now = now or timezone.now()
    if exam.end_time and exam.end_time <= now:
        return 'ended'
    if exam.is_active:
        return 'live'
    return 'draft'


def results_final_at(exam, finished_at, now=None):
    """When a student's results on this exam stopped changing: when they submitted the exam
    (ExamEnrollment.finished_at) or when the exam ended, whichever came first. None while
    they can still submit."""
    from django.utils import timezone
    now = now or timezone.now()
    ended_at = exam.end_time if exam_status(exam, now) == 'ended' else None
    return min((t for t in (finished_at, ended_at) if t), default=None)


class Exam(models.Model):  # one exam created by a trainer
    title = models.CharField(max_length=200)  # short name of the exam, stored as varchar(200) in postgres
    description = models.TextField(blank=True)  # optional long text, blank=True means not required
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exams')  # which trainer created this; CASCADE means if user deleted, their exams delete too
    duration_minutes = models.PositiveIntegerField(default=60)  # how long students have; PositiveIntegerField rejects negatives
    is_active = models.BooleanField(default=False)  # False = draft, True = live; trainer publishes manually
    start_time = models.DateTimeField(null=True, blank=True)  # if set, exam auto-opens at this time
    end_time = models.DateTimeField(null=True, blank=True)    # if set, exam auto-closes at this time (triggers plagiarism batch)
    sections = models.JSONField(default=list, blank=True)  # who takes it: section names (User.cohort); empty = the whole cohort
    created_at = models.DateTimeField(auto_now_add=True)  # auto-set to current timestamp on creation, never changes

    def __str__(self):
        return self.title  # shows exam title in admin instead of "Exam object (1)"

    def save(self, *args, **kwargs):
        # Opened with no schedule: it starts now. Every dashboard orders and dates exams by start_time.
        if self.is_active and self.start_time is None:
            from django.utils import timezone
            self.start_time = timezone.now()
            if kwargs.get('update_fields') is not None:
                kwargs['update_fields'] = {*kwargs['update_fields'], 'start_time'}
        super().save(*args, **kwargs)

    def audience(self):
        """Students this exam is for: its sections, or every student when none are picked."""
        from django.contrib.auth import get_user_model
        students = get_user_model().objects.filter(role='student')
        return students.filter(cohort__in=self.sections) if self.sections else students

    def enroll_audience(self) -> int:
        """Enroll every student in the audience who isn't enrolled yet. Never removes anyone."""
        rows = [ExamEnrollment(exam=self, student=s) for s in self.audience()]
        return len(ExamEnrollment.objects.bulk_create(rows, ignore_conflicts=True))


class Question(models.Model):
    LANGUAGE_CHOICES = [
        ('python', 'Python'),
        ('javascript', 'JavaScript'),
    ]
    DIFFICULTY_CHOICES = [
        ('easy', 'Easy'),
        ('medium', 'Medium'),
        ('hard', 'Hard'),
    ]
    POINTS_MAP = {'easy': 10, 'medium': 20, 'hard': 30}

    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='questions')
    title = models.CharField(max_length=300)
    description = models.TextField()
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='javascript')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')
    tags = models.CharField(max_length=200, blank=True)  # comma-separated e.g. "string,two-pointer"
    max_attempts = models.PositiveIntegerField(default=3)
    # Editor starter code (input reading done for the student); empty = the generic starter
    starter_code_javascript = models.TextField(blank=True, default='')
    starter_code_python = models.TextField(blank=True, default='')
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def points(self) -> int:
        return self.POINTS_MAP.get(self.difficulty, 20)

    def __str__(self):
        return self.title  # shows question title in admin and logs


class ExamEnrollment(models.Model):
    exam = models.ForeignKey(Exam, on_delete=models.CASCADE, related_name='enrollments')
    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='enrollments')
    enrolled_at = models.DateTimeField(auto_now_add=True)
    finished_at = models.DateTimeField(null=True, blank=True)  # the student pressed End exam: no more submissions

    class Meta:
        unique_together = ('exam', 'student')  # no duplicate enrollments

    def __str__(self):
        return f"{self.student.username} → {self.exam.title}"


class TestCase(models.Model):  # one input/output pair used to judge if student code is correct
    question = models.ForeignKey(Question, on_delete=models.CASCADE, related_name='test_cases')  # which question this belongs to
    input_data = models.TextField()  # what gets passed to student's program as stdin
    expected_output = models.TextField()  # what the program must print to pass this test case
    is_hidden = models.BooleanField(default=True)  # True = student never sees this; trainer's secret judge

    def __str__(self):
        return f"TestCase for {self.question.title}"  # readable label in admin
