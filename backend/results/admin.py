from django.contrib import admin
from .models import Result

@admin.register(Result)
class ResultAdmin(admin.ModelAdmin):
    list_display = ['id', 'submission', 'test_case', 'passed', 'execution_time_ms']
    list_filter = ['passed']
