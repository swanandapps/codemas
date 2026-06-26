from django.contrib import admin  # Django admin registry
from .models import RubricScore, AIHint


@admin.register(RubricScore)
class RubricScoreAdmin(admin.ModelAdmin):
    list_display = ('submission', 'total_score', 'model_used', 'created_at')
    readonly_fields = ('created_at',)


@admin.register(AIHint)
class AIHintAdmin(admin.ModelAdmin):
    list_display = ('submission', 'model_used', 'created_at')
    readonly_fields = ('created_at',)
