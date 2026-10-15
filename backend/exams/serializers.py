from rest_framework import serializers  # DRF serializer base classes
from .models import Exam, Question, TestCase  # our models

STAFF_ROLES = ('trainer', 'admin')


def sees_hidden_tests(user):
    """Only staff may read a hidden test's input/expected output. Anyone else
    (students, unknown roles, anonymous) gets the redacted stub."""
    return getattr(user, 'role', None) in STAFF_ROLES


class TestCaseSerializer(serializers.ModelSerializer):  # serializes test cases
    class Meta:
        model = TestCase
        fields = ['id', 'input_data', 'expected_output', 'is_hidden']  # is_hidden included so trainer can see which are hidden

    def to_representation(self, instance):
        # Hidden tests are the trainer's secret judge: non-staff get only {id, is_hidden}
        # so the count stays right but no input or expected output ever leaves the server.
        # Redact unless the caller explicitly says the viewer is staff (safe by default).
        if instance.is_hidden and not self.context.get('show_hidden', False):
            return {'id': instance.id, 'is_hidden': True}
        return super().to_representation(instance)


class QuestionSerializer(serializers.ModelSerializer):
    test_cases = TestCaseSerializer(many=True, read_only=True)
    starter_code = serializers.SerializerMethodField()
    points = serializers.IntegerField(read_only=True)
    # The limit the server enforces: the policy's max attempts, applied to every question
    # (Question.max_attempts is not enforced, so it is never shown).
    max_attempts = serializers.SerializerMethodField()

    class Meta:
        model = Question
        fields = ['id', 'title', 'description', 'language', 'difficulty', 'tags', 'max_attempts', 'points', 'test_cases',
                  'starter_code', 'starter_code_javascript', 'starter_code_python']
        extra_kwargs = {  # raw starters are write-only; readers get `starter_code` with the generic fallback
            'starter_code_javascript': {'write_only': True, 'required': False},
            'starter_code_python': {'write_only': True, 'required': False},
        }

    def get_max_attempts(self, obj):
        if 'attempt_limit' not in self.context:   # once per request, shared by every question
            from plagiarism.models import PlagiarismPolicy
            self.context['attempt_limit'] = PlagiarismPolicy.get().max_attempts
        return self.context['attempt_limit']

    def get_starter_code(self, obj):
        from .starter_code import for_question
        return for_question(obj)


class ExamSerializer(serializers.ModelSerializer):  # serializes exam with nested questions
    questions = QuestionSerializer(many=True, read_only=True)  # nest all questions inside exam
    created_by = serializers.StringRelatedField()  # shows username instead of user id
    status = serializers.SerializerMethodField()  # draft / live / ended, the same rule as every exam page

    class Meta:
        model = Exam
        fields = ['id', 'title', 'description', 'created_by', 'duration_minutes', 'is_active', 'start_time', 'end_time', 'status', 'sections', 'created_at', 'questions']

    def get_status(self, obj):
        from .models import exam_status
        return exam_status(obj)


class ExamCreateSerializer(serializers.ModelSerializer):  # used only for creating/updating exams
    class Meta:
        model = Exam
        fields = ['id', 'title', 'description', 'duration_minutes', 'is_active', 'start_time', 'end_time', 'sections']
        read_only_fields = ['id']

    def validate_sections(self, value):
        if not isinstance(value, list) or not all(isinstance(s, str) and s.strip() for s in value):
            raise serializers.ValidationError('sections must be a list of section names')
        return sorted({s.strip() for s in value})
