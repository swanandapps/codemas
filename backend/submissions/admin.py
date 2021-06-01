from django.contrib import admin
from .models import Submission

@admin.register(Submission)
class SubmissionAdmin(admin.ModelAdmin):
    list_display = ['id', 'student', 'exam', 'question', 'language', 'status', 'attempt_number', 'submitted_at']
    list_filter = ['status', 'language', 'exam']
    search_fields = ['student__username']
