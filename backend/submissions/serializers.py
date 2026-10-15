from rest_framework import serializers
from .models import Submission

SUPPORTED_LANGUAGES = ('javascript', 'python')

class SubmissionSerializer(serializers.ModelSerializer):
    student_username = serializers.CharField(source='student.username', read_only=True)
    student_id = serializers.IntegerField(source='student.id', read_only=True)
    question_title = serializers.CharField(source='question.title', read_only=True)
    question_description = serializers.CharField(source='question.description', read_only=True)
    exam_title = serializers.CharField(source='exam.title', read_only=True)
    percent_time_used = serializers.FloatField(read_only=True)
    # Set by the list view's annotation; None where a view doesn't annotate
    tests_passed = serializers.SerializerMethodField()
    tests_total = serializers.SerializerMethodField()

    class Meta:
        model = Submission
        fields = [
            'id', 'student_username', 'student_id', 'exam', 'exam_title', 'question', 'question_title', 'question_description',
            'code', 'language', 'attempt_number', 'status',
            'submitted_at', 'time_remaining_seconds',
            'execution_time_ms', 'plagiarism_score',
            'ip_address', 'percent_time_used',
            'behavioural_check_done', 'similarity_check_done',
            'tests_passed', 'tests_total',
        ]

    def get_tests_passed(self, obj):
        return getattr(obj, 'tests_passed', None)

    def get_tests_total(self, obj):
        return getattr(obj, 'tests_total', None)

class SubmissionCreateSerializer(serializers.ModelSerializer):
    class Meta:
        model = Submission
        fields = [
            'question', 'code', 'language', 'time_remaining_seconds',
            'had_paste_event', 'paste_char_count', 'time_to_complete_seconds',
            'tab_switch_count',
        ]

    def validate_language(self, value):
        # Only the languages the course teaches; C++ and Java were never offered to students
        if value not in SUPPORTED_LANGUAGES:
            raise serializers.ValidationError('Only JavaScript and Python are supported.')
        return value
