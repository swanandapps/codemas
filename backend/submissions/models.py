from django.db import models  # base module for all Django model fields
from django.conf import settings  # to reference AUTH_USER_MODEL safely


class Submission(models.Model):
    STATUS_CHOICES = [  # tracks where this submission is in the pipeline
        ('pending', 'Pending'),        # just received, not yet queued
        ('running', 'Running'),        # Docker container is executing it
        ('passed', 'Passed'),          # all test cases passed
        ('failed', 'Failed'),          # one or more test cases failed
        ('error', 'Error'),            # code threw an exception or timed out
    ]

    student = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='submissions')  # who submitted
    exam = models.ForeignKey('exams.Exam', on_delete=models.CASCADE, related_name='submissions')  # which exam
    question = models.ForeignKey('exams.Question', on_delete=models.CASCADE, related_name='submissions')  # which question
    code = models.TextField()  # the actual code the student submitted
    language = models.CharField(max_length=20)  # which language they used
    attempt_number = models.PositiveIntegerField()  # 1st, 2nd or 3rd attempt — enforced server side
    status = models.CharField(max_length=10, choices=STATUS_CHOICES, default='pending')  # current state in the pipeline
    submitted_at = models.DateTimeField(auto_now_add=True)  # exact timestamp of submission
    time_remaining_seconds = models.PositiveIntegerField(null=True, blank=True)  # seconds left on exam clock at submission time
    execution_time_ms = models.PositiveIntegerField(null=True, blank=True)  # how long student code ran in Docker, null until execution completes
    plagiarism_score = models.FloatField(null=True, blank=True)  # 0.0 to 1.0, populated async after submission, null until checked
    behavioural_check_done = models.BooleanField(default=False)  # True once run_behavioural_check has completed
    similarity_check_done  = models.BooleanField(default=False)  # True once run_question_plagiarism_check has included this submission
    normalized_code        = models.TextField(blank=True, default='')  # pre-normalized at submission time, reused for every similarity search
    ip_address = models.GenericIPAddressField(null=True, blank=True)  # where submission came from, catches proxy submissions
    # behaviour signals — captured by frontend, sent with submission
    had_paste_event = models.BooleanField(default=False)       # did student paste at any point
    paste_char_count = models.IntegerField(default=0)          # total characters pasted
    time_to_complete_seconds = models.IntegerField(default=0)  # seconds from exam start to submission
    tab_switch_count = models.IntegerField(default=0)          # how many times student left the exam tab


    class Meta:  # extra database-level configuration
        ordering = ['-submitted_at']  # newest submissions first by default

    def __str__(self):
        return f"{self.student.username} | Q{self.question.id} | attempt {self.attempt_number}"

    @property
    def percent_time_used(self):  # computed on the fly, never stored — avoids stale derived data
        if self.time_remaining_seconds is None:
            return None
        total_seconds = self.exam.duration_minutes * 60
        return round((total_seconds - self.time_remaining_seconds) / total_seconds * 100, 1)
