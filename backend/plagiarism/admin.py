from django.contrib import admin
from .models import PlagiarismFlag

@admin.register(PlagiarismFlag)
class PlagiarismFlagAdmin(admin.ModelAdmin):
    list_display = ['id', 'submission_1', 'submission_2', 'similarity_score', 'flagged', 'review_status']
    list_filter = ['flagged', 'review_status']
