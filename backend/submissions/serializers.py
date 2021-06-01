from rest_framework import serializers
from .models import Submission

class SubmissionSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    question_title = serializers.CharField(source='question.title', read_only=True)
    question_description = serializers.CharField(source='question.description', read_only=True)
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    percent_time_used = serializers.FloatField(read_only=True)

    class Meta:
        model = Submission
        fields = [
            'id', 'student_username', 'exam', 'exam_title', 'question', 'question_title', 'question_description',
            'code', 'language', 'attempt_number', 'status',
            'submitted_at', 'time_remaining_seconds',
            'execution_time_ms', 'plagiarism_score',
            'ip_address', 'percent_time_used',
            'behavioural_check_done', 'similarity_check_done',
        ]

class SubmissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = [
            'question', 'code', 'language', 'time_remaining_seconds',
            'had_paste_event', 'paste_char_count', 'time_to_complete_seconds',
            'tab_switch_count',
        ]
