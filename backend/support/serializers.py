from rest_framework import serializers
from .models import DisputeRequest


class DisputeRequestSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    resolved_by_username = serializers.CharField(source='resolved_by.username', read_only=True)

    class Meta:
        model = DisputeRequest
        fields = [
            'id', 'student', 'student_username', 'flag_type', 'flag_id',
            'student_note', 'status', 'resolved_by', 'resolved_by_username',
            'resolution_note', 'created_at', 'resolved_at',
        ]
        read_only_fields = ['id', 'student', 'status', 'resolved_by', 'resolved_at', 'created_at']
