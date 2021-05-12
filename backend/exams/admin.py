from django.contrib import admin
from .models import Exam, Question, TestCase

@admin.register(Exam)
class ExamAdmin(admin.ModelAdmin):
    list_display = ['title', 'duration_minutes', 'is_active', 'created_at']
    list_filter = ['is_active']
    search_fields = ['title']

@admin.register(Question)
class QuestionAdmin(admin.ModelAdmin):
    list_display = ['title', 'exam', 'max_attempts', 'created_at']
    list_filter = ['exam']
    search_fields = ['title']

@admin.register(TestCase)
class TestCaseAdmin(admin.ModelAdmin):
    list_display = ['question', 'input_data', 'expected_output', 'is_hidden']
    list_filter = ['question', 'is_hidden']
