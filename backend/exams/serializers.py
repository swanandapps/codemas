from rest_framework import serializers  # DRF serializer base classes
from .models import Exam, Question, TestCase  # our models


class TestCaseSerializer(serializers.ModelSerializer):  # serializes test cases
    class Meta:
        model = TestCase
        fields = ['id', 'input_data', 'expected_output', 'is_hidden']  # is_hidden included so trainer can see which are hidden


class QuestionSerializer(serializers.ModelSerializer):
    test_cases = TestCaseSerializer(many=True, read_only=True)
    points = serializers.IntegerField(read_only=True)

    class Meta:
        model = Question
        fields = ['id', 'title', 'description', 'language', 'difficulty', 'tags', 'max_attempts', 'points', 'test_cases']


class ExamSerializer(serializers.ModelSerializer):  # serializes exam with nested questions
    questions = QuestionSerializer(many=True, read_only=True)  # nest all questions inside exam
    created_by = serializers.StringRelatedField()  # shows username instead of user id

    class Meta:
        model = Exam
        fields = ['id', 'title', 'description', 'created_by', 'duration_minutes', 'is_active', 'created_at', 'questions']


class ExamCreateSerializer(serializers.ModelSerializer):  # used only for creating/updating exams
    class Meta:
        model = Exam
        fields = ['id', 'title', 'description', 'duration_minutes', 'is_active']
        read_only_fields = ['id']
