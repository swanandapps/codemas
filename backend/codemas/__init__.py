from .celery import app as celery_app  # load Celery when Django starts

__all__ = ('celery_app',)  # make celery_app available when this package is imported
