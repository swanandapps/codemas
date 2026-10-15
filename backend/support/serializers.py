from rest_framework import serializers
from .models import DisputeRequest


class DisputeRequestSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    resolved_by_username = serializers.CharField(source='resolved_by.username', read_only=True)
    exam_id = serializers.IntegerField(read_only=True)
    exam_title = serializers.CharField(source='exam.title', read_only=True, default=None)

    class Meta:
        model = DisputeRequest
        fields = [
            'id', 'student', 'student_username', 'exam_id', 'exam_title',
            'flag_type', 'flag_id',   # legacy per-flag disputes only
            'student_note', 'decision_note', 'status', 'resolved_by', 'resolved_by_username',
            'resolution_note', 'created_at', 'resolved_at',
        ]
        read_only_fields = fields


class MyAppealSerializer(serializers.ModelSerializer):
    """A student's own appeal: no trainer identities."""
    exam_id = serializers.IntegerField(read_only=True)
    exam_title = serializers.CharField(source='exam.title', read_only=True, default=None)

    class Meta:
        model = DisputeRequest
        fields = ['id', 'exam_id', 'exam_title', 'status', 'student_note', 'decision_note',
                  'resolution_note', 'created_at', 'resolved_at']
        read_only_fields = fields
