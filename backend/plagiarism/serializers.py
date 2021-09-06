from rest_framework import serializers
from .models import PlagiarismFlag, BehaviouralFlag, PlagiarismPolicy, ReviewAuditLog


class PlagiarismFlagSerializer(serializers.ModelSerializer):
    submission_1_student    = serializers.CharField(source='submission_1.student.username', read_only=True)
    submission_1_student_id = serializers.IntegerField(source='submission_1.student.id', read_only=True)
    submission_2_student    = serializers.CharField(source='submission_2.student.username', read_only=True)
    submission_2_student_id = serializers.IntegerField(source='submission_2.student.id', read_only=True)
    question_title          = serializers.CharField(source='submission_1.question.title', read_only=True)
    question_difficulty     = serializers.CharField(source='submission_1.question.difficulty', read_only=True)
    exam_title              = serializers.CharField(source='submission_1.exam.title', read_only=True)
    exam_id                 = serializers.IntegerField(source='submission_1.exam.id', read_only=True)
    submission_1_attempt    = serializers.IntegerField(source='submission_1.attempt_number', read_only=True)
    submission_1_language   = serializers.CharField(source='submission_1.language', read_only=True)
    submission_1_status     = serializers.CharField(source='submission_1.status', read_only=True)
    submission_2_attempt    = serializers.IntegerField(source='submission_2.attempt_number', read_only=True)
    submission_2_language   = serializers.CharField(source='submission_2.language', read_only=True)
    submission_2_status     = serializers.CharField(source='submission_2.status', read_only=True)

    class Meta:
        model = PlagiarismFlag
        fields = [
            'id', 'submission_1', 'submission_1_student', 'submission_1_student_id',
            'submission_1_attempt', 'submission_1_language', 'submission_1_status',
            'submission_2', 'submission_2_student', 'submission_2_student_id',
            'submission_2_attempt', 'submission_2_language', 'submission_2_status',
            'question_title', 'question_difficulty', 'exam_title', 'exam_id',
            'similarity_score', 'flagged', 'detection_method',
            'checked_at', 'review_status', 'review_note', 'reviewed_by',
        ]
        read_only_fields = ['submission_1', 'submission_2', 'similarity_score', 'detection_method', 'checked_at']


class BehaviouralFlagSerializer(serializers.ModelSerializer):
    student             = serializers.CharField(source='submission.student.username', read_only=True)
    student_id          = serializers.IntegerField(source='submission.student.id', read_only=True)
    question_title      = serializers.CharField(source='submission.question.title', read_only=True)
    question_difficulty = serializers.CharField(source='submission.question.difficulty', read_only=True)
    exam_title          = serializers.CharField(source='submission.exam.title', read_only=True)
    exam_id             = serializers.IntegerField(source='submission.exam.id', read_only=True)
    submission_id       = serializers.IntegerField(source='submission.id', read_only=True)
    attempt_number      = serializers.IntegerField(source='submission.attempt_number', read_only=True)
    submission_status   = serializers.CharField(source='submission.status', read_only=True)
    language            = serializers.CharField(source='submission.language', read_only=True)
    submitted_at        = serializers.DateTimeField(source='submission.submitted_at', read_only=True)

    class Meta:
        model = BehaviouralFlag
        fields = [
            'id', 'submission', 'submission_id',
            'student', 'student_id',
            'question_title', 'question_difficulty',
            'exam_title', 'exam_id',
            'attempt_number', 'submission_status', 'language', 'submitted_at',
            'risk_score', 'confidence',
            'paste_score', 'time_score', 'snapshot_score', 'submission_score',
            'signals_triggered',
            'review_status', 'review_note', 'reviewed_by',
            'created_at',
        ]
        read_only_fields = [
            'submission', 'risk_score', 'confidence',
            'paste_score', 'time_score', 'snapshot_score', 'submission_score',
            'signals_triggered', 'created_at',
        ]


class PlagiarismPolicySerializer(serializers.ModelSerializer):
    class Meta:
        model = PlagiarismPolicy
        fields = [
            'paste_weight', 'time_weight', 'tab_weight', 'submission_weight',
            'min_risk_score', 'similarity_threshold',
            'easy_baseline_s', 'medium_baseline_s', 'hard_baseline_s',
            'max_attempts',
            'updated_at',
        ]
        read_only_fields = ['updated_at']


class ReviewAuditLogSerializer(serializers.ModelSerializer):
    reviewed_by_username = serializers.CharField(source='reviewed_by.username', read_only=True)

    class Meta:
        model = ReviewAuditLog
        fields = ['id', 'flag_type', 'flag_id', 'action', 'note', 'reviewed_by_username', 'created_at']
