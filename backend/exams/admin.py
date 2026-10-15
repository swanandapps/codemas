from django.contrib import admin
from .models import Exam, ExamEnrollment, Question, TestCase

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

@admin.register(ExamEnrollment)
class ExamEnrollmentAdmin(admin.ModelAdmin):  # ops path for enrolling students (no enroll UI in the app)
    list_display = ['student', 'exam', 'enrolled_at', 'finished_at']
    list_filter = ['exam']
    search_fields = ['student__username', 'exam__title']
    autocomplete_fields = ['exam', 'student']
