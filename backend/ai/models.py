from django.db import models  # base module for all Django model fields


class RubricScore(models.Model):
    """GPT-generated qualitative evaluation of a submission.

    Produced async AFTER the test-case result is delivered to the student — this
    never sits on the sub-10s result path. One row per submission.
    """
    submission = models.OneToOneField(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='rubric_score',  # submission.rubric_score
    )

    # Four dimensions, each scored 0-2 with a one-sentence justification.
    correctness_score = models.PositiveSmallIntegerField()          # how well it passes the tests
    correctness_note = models.TextField()
    code_quality_score = models.PositiveSmallIntegerField()         # readability, naming, structure
    code_quality_note = models.TextField()
    approach_score = models.PositiveSmallIntegerField()             # optimality / reasoning of the algorithm
    approach_note = models.TextField()
    edge_case_score = models.PositiveSmallIntegerField()            # boundary-condition handling
    edge_case_note = models.TextField()

    overall_feedback = models.TextField()                          # 2-3 constructive sentences
    model_used = models.CharField(max_length=60, blank=True)       # which GPT model produced this
    created_at = models.DateTimeField(auto_now_add=True)

    @property
    def total_score(self):
        """Sum of the four dimensions, 0-8."""
        return (
            self.correctness_score + self.code_quality_score
            + self.approach_score + self.edge_case_score
        )

    def __str__(self):
        return f"RubricScore(sub={self.submission_id}, total={self.total_score}/8)"


class AIHint(models.Model):
    """GPT-generated Socratic hint for a FAILED submission.

    Generated async after the failed result is delivered. One row per submission;
    stored so it does not regenerate on page refresh. Shown only on demand
    (student clicks "Show Hint").
    """
    submission = models.OneToOneField(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='ai_hint',  # submission.ai_hint
    )
    hint = models.TextField()                                  # 1-3 sentence Socratic nudge
    model_used = models.CharField(max_length=60, blank=True)   # which GPT model produced this
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"AIHint(sub={self.submission_id})"
