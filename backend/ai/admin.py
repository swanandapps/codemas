from django.contrib import admin  # Django admin registry
from .models import RubricScore


@admin.register(RubricScore)
class RubricScoreAdmin(admin.ModelAdmin):
    list_display = ('submission', 'total_score', 'model_used', 'created_at')
    readonly_fields = ('created_at',)
