import os  # to read environment variables
from celery import Celery  # Celery application class

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'codemas.settings')  # tell Celery which Django settings to use

app = Celery('codemas')  # create Celery app named codemas
app.config_from_object('django.conf:settings', namespace='CELERY')  # load Celery config from Django settings — reads all CELERY_ prefixed settings
app.autodiscover_tasks()  # automatically find tasks.py in every installed app
