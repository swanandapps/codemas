from django.contrib import admin

from .models import Job


@admin.register(Job)
class JobAdmin(admin.ModelAdmin):
    """Read-only view of the outbox. This is what you open when asked "show me the outbox table"."""
    list_display = ('id', 'kind', 'subject_id', 'status', 'attempt', 'published_at', 'started_at',
                    'finished_at', 'lease_expires_at', 'created_at')
    list_filter = ('status', 'kind')
    search_fields = ('=subject_id', '=id')
    ordering = ('-created_at',)
    readonly_fields = [f.name for f in Job._meta.fields]

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
