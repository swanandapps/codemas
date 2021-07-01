from django.db import models  # base module for all Django model fields


class Result(models.Model):
    submission = models.ForeignKey('submissions.Submission', on_delete=models.CASCADE, related_name='results')  # which submission this result belongs to
    test_case = models.ForeignKey('exams.TestCase', on_delete=models.CASCADE, related_name='results')  # which specific test case was run
    passed = models.BooleanField()  # did the student's output match expected output
    actual_output = models.TextField(blank=True)  # what the student's code actually printed
    execution_time_ms = models.PositiveIntegerField(null=True, blank=True)  # how long this specific test case took to run
    error_message = models.TextField(blank=True)  # if code crashed, the error traceback goes here

#Meta is a special Django convention. It's not a real class in the traditional sense — it's a container for configuration about the model itself, not data.
#Think of it as: Result is the table definition, Meta is the table settings.
    class Meta:
        unique_together = ('submission', 'test_case')  # one result per test case per submission, no duplicates unique_together tells Postgres: the combination of these two columns must be unique across the table.

    def __str__(self):
        status = 'PASS' if self.passed else 'FAIL'
        return f"{self.submission} | TC{self.test_case.id} | {status}"
