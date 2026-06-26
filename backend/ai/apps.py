from django.apps import AppConfig  # base class for app configuration


class AiConfig(AppConfig):
    default_auto_field = 'django.db.models.BigAutoField'
    name = 'ai'  # importable app label — used in INSTALLED_APPS and migrations
    verbose_name = 'AI Features'  # all three async GPT features live here
