import os
from celery import Celery

# Set default Django settings module for celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# Namespace='CELERY' means all Celery settings must be prefixed with 'CELERY_'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Automatically discover tasks.py in all installed apps (like app/tasks.py)
app.autodiscover_tasks()
