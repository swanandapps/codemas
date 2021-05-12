from django.db import models  # base module for all Django model fields
from django.conf import settings  # lets us reference AUTH_USER_MODEL without importing User directly


class Exam(models.Model):  # one exam created by a trainer
    title = models.CharField(max_length=200)  # short name of the exam, stored as varchar(200) in postgres
    description = models.TextField(blank=True)  # optional long text, blank=True means not required
    created_by = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='exams')  # which trainer created this; CASCADE means if user deleted, their exams delete too
    duration_minutes = models.PositiveIntegerField(default=60)  # how long students have; PositiveIntegerField rejects negatives
    is_active = models.BooleanField(default=False)  # False = draft, True = live; trainer publishes manually
    start_time = models.DateTimeField(null=True, blank=True)  # if set, exam auto-opens at this time
    end_time = models.DateTimeField(null=True, blank=True)    # if set, exam auto-closes at this time (triggers plagiarism batch)
    created_at = models.DateTimeField(auto_now_add=True)  # auto-set to current timestamp on creation, never changes

    def __str__(self):
        return self.title  # shows exam title in admin instead of "Exam object (1)"


class Question(models.Model):
    LANGUAGE_CHOICES = [
        ('python', 'Python'),
        ('javascript', 'JavaScript'),
        ('java', 'Java'),
        ('cpp', 'C++'),
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
    language = models.CharField(max_length=20, choices=LANGUAGE_CHOICES, default='python')
    difficulty = models.CharField(max_length=10, choices=DIFFICULTY_CHOICES, default='medium')
    tags = models.CharField(max_length=200, blank=True)  # comma-separated e.g. "string,two-pointer"
    max_attempts = models.PositiveIntegerField(default=3)
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
