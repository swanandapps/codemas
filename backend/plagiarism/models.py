from django.db import models
from django.conf import settings


class PlagiarismPolicy(models.Model):
    """
    Singleton configuration table — trainers set detection thresholds from UI.
    Use PlagiarismPolicy.get() to retrieve; only ever one row exists.
    """
    paste_weight        = models.FloatField(default=0.40)
    time_weight         = models.FloatField(default=0.30)
    tab_weight          = models.FloatField(default=0.15)
    submission_weight   = models.FloatField(default=0.15)

    min_risk_score      = models.FloatField(default=0.20)
    similarity_threshold = models.FloatField(default=0.80)

    easy_baseline_s     = models.IntegerField(default=90)
    medium_baseline_s   = models.IntegerField(default=240)
    hard_baseline_s     = models.IntegerField(default=480)

    max_attempts        = models.PositiveIntegerField(default=3)

    updated_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='policy_updates',
    )
    updated_at = models.DateTimeField(auto_now=True)

    @classmethod
    def get(cls):
        obj, _ = cls.objects.get_or_create(pk=1)
        return obj

    def __str__(self):
        return 'Plagiarism Policy'


POLICY_FIELDS = [
    'paste_weight', 'time_weight', 'tab_weight', 'submission_weight',
    'min_risk_score', 'similarity_threshold',
    'easy_baseline_s', 'medium_baseline_s', 'hard_baseline_s',
    'max_attempts',
]


class PolicyVersion(models.Model):
    """Snapshot of PlagiarismPolicy state at every change — used for audit and dispute resolution."""
    changed_by      = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL,
        null=True, related_name='policy_versions',
    )
    changed_at      = models.DateTimeField(auto_now_add=True)
    change_reason   = models.TextField(blank=True)
    snapshot_before = models.JSONField()
    snapshot_after  = models.JSONField()

    class Meta:
        ordering = ['-changed_at']

    def __str__(self):
        return f'PolicyVersion by {self.changed_by_id} at {self.changed_at}'


class ReviewAuditLog(models.Model):
    FLAG_TYPE_CHOICES = [('behavioural', 'Behavioural'), ('similarity', 'Similarity')]

    flag_type   = models.CharField(max_length=20, choices=FLAG_TYPE_CHOICES)
    flag_id     = models.IntegerField()
    action      = models.CharField(max_length=20)
    note        = models.TextField(blank=True)
    reviewed_by = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name='audit_logs',
    )
    created_at  = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['-created_at']

    def __str__(self):
        return f'{self.reviewed_by.username} {self.action} {self.flag_type}#{self.flag_id}'


class BehaviouralFlag(models.Model):
    """
    Flags a single student's submission based on their own behaviour —
    no cross-comparison with other students needed.

    Each signal is stored as a float (0.0–1.0) so trainers can see
    exactly which signals fired and how strongly. The signals_triggered
    field stores human-readable explanations so the trainer doesn't need
    to interpret numbers.

    This runs O(1) per submission — cost doesn't grow with class size.
    """
    CONFIDENCE_CHOICES = [
        ('low',    'Low'),     # 1 signal triggered
        ('medium', 'Medium'),  # 2 signals triggered
        ('high',   'High'),    # 3+ signals triggered
    ]

    submission = models.OneToOneField(
        'submissions.Submission',
        on_delete=models.CASCADE,
        related_name='behavioural_flag',
    )
    risk_score = models.FloatField()           # weighted average of all signal scores, 0.0–1.0
    confidence = models.CharField(max_length=10, choices=CONFIDENCE_CHOICES)

    # individual signal scores — stored separately so trainers can audit each one
    paste_score        = models.FloatField(default=0.0)  # paste ratio signal
    time_score         = models.FloatField(default=0.0)  # time-to-complete vs difficulty baseline
    snapshot_score     = models.FloatField(default=0.0)  # code growth in last N minutes
    submission_score   = models.FloatField(default=0.0)  # code change between own attempts

    # human-readable list of triggered signals — shown in trainer UI
    # e.g. ["Pasted 68% of code", "Solved hard problem in 2m 14s"]
    signals_triggered = models.JSONField(default=list)

    review_status = models.CharField(
        max_length=10,
        choices=[('pending','Pending'),('confirmed','Confirmed'),('dismissed','Dismissed')],
        default='pending',
    )
    review_note   = models.TextField(blank=True)
    reviewed_by   = models.ForeignKey(
        settings.AUTH_USER_MODEL, null=True, blank=True,
        on_delete=models.SET_NULL, related_name='behavioural_reviews',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f"BehaviouralFlag: {self.submission.student.username} | {self.confidence} | {self.risk_score:.2f}"


class PlagiarismRun(models.Model):
    """
    Audit record for every plagiarism check execution.
    Captures the policy in effect, exam performance metrics, and detection results
    so admins can clearly see what each policy change produced.
    """
    TRIGGER_CHOICES = [('exam_close', 'Exam Close'), ('manual_rerun', 'Manual Rerun')]
    STATUS_CHOICES  = [('running', 'Running'), ('completed', 'Completed'), ('failed', 'Failed')]

    exam         = models.ForeignKey('exams.Exam', on_delete=models.CASCADE, related_name='plagiarism_runs')
    triggered_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL)
    trigger      = models.CharField(max_length=20, choices=TRIGGER_CHOICES, default='exam_close')
    status       = models.CharField(max_length=20, choices=STATUS_CHOICES, default='running')
    ran_at       = models.DateTimeField(auto_now_add=True)
    completed_at = models.DateTimeField(null=True, blank=True)

    # Full policy snapshot at time of run
    policy_snapshot = models.JSONField(default=dict)

    # Exam performance context (from submissions — fixed, doesn't change between runs)
    total_submissions  = models.IntegerField(default=0)
    unique_students    = models.IntegerField(default=0)
    pass_rate          = models.FloatField(null=True, blank=True)   # % of students who passed ≥1 question
    avg_execution_ms   = models.FloatField(null=True, blank=True)   # avg Docker execution time
    avg_solve_time_s   = models.FloatField(null=True, blank=True)   # avg time_to_complete_seconds for passed submissions
    avg_attempts       = models.FloatField(null=True, blank=True)   # avg attempt_number per student
    avg_time_remaining = models.FloatField(null=True, blank=True)   # avg seconds left on clock at submission

    # Behavioural phase results
    b_flags_total      = models.IntegerField(default=0)
    b_flags_new        = models.IntegerField(default=0)   # created this run (vs updated)
    b_high_confidence  = models.IntegerField(default=0)
    b_medium_confidence= models.IntegerField(default=0)
    b_low_confidence   = models.IntegerField(default=0)
    b_avg_risk_score   = models.FloatField(null=True, blank=True)

    # Similarity phase results (updated atomically by per-question tasks)
    s_flags_total      = models.IntegerField(default=0)
    s_flags_new        = models.IntegerField(default=0)
    s_pairs_90_plus    = models.IntegerField(default=0)   # similarity ≥ 0.90
    s_pairs_80_90      = models.IntegerField(default=0)   # 0.80 ≤ similarity < 0.90
    s_avg_similarity   = models.FloatField(null=True, blank=True)
    questions_total    = models.IntegerField(default=0)
    questions_done     = models.IntegerField(default=0)

    class Meta:
        ordering = ['-ran_at']

    def __str__(self):
        return f'PlagiarismRun exam={self.exam_id} at {self.ran_at}'


class PlagiarismFlag(models.Model):
    REVIEW_STATUS_CHOICES = [  # tracks human review decision on the flag
        ('pending', 'Pending'),      # algorithm flagged, no human reviewed yet
        ('confirmed', 'Confirmed'),  # trainer confirmed this is plagiarism
        ('dismissed', 'Dismissed'),  # trainer dismissed, false positive
    ]

    submission_1 = models.ForeignKey('submissions.Submission', on_delete=models.CASCADE, related_name='plagiarism_as_first')  # first submission in the comparison pair
    submission_2 = models.ForeignKey('submissions.Submission', on_delete=models.CASCADE, related_name='plagiarism_as_second')  # second submission being compared against
    similarity_score = models.FloatField()  # cosine similarity score between 0.0 and 1.0
    flagged = models.BooleanField(default=False)  # True if score exceeds threshold of 0.85
    detection_method = models.CharField(max_length=50, default='cosine_similarity')  # which algorithm detected this — auditable as methods evolve
    checked_at = models.DateTimeField(auto_now_add=True)  # when the algorithmic comparison ran
    flagged_at = models.DateTimeField(null=True, blank=True)  # when a human trainer confirmed the flag
    reviewed_by = models.ForeignKey(settings.AUTH_USER_MODEL, null=True, blank=True, on_delete=models.SET_NULL, related_name='plagiarism_reviews')  # which trainer reviewed this flag
    review_status = models.CharField(max_length=10, choices=REVIEW_STATUS_CHOICES, default='pending')  # human decision on this flag
    review_note = models.TextField(blank=True)  # trainer's written reason for confirming or dismissing

    class Meta:
        unique_together = ('submission_1', 'submission_2')  # never compare the same pair twice

    def __str__(self):
        return f"Flag: {self.submission_1} vs {self.submission_2} | {self.similarity_score} | {self.review_status}"
