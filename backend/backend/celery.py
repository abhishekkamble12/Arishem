import os

from celery import Celery
from celery.signals import worker_process_init

# Set default Django settings module for celery
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'backend.settings')

app = Celery('backend')

# Namespace='CELERY' means all Celery settings must be prefixed with 'CELERY_'
app.config_from_object('django.conf:settings', namespace='CELERY')

# Automatically discover tasks.py in all installed apps (like app/tasks.py)
app.autodiscover_tasks()


@worker_process_init.connect
def _warm_up_worker(**_kwargs):
    """
    Load the embedding model when a worker process starts, so the first document
    ingested is not also the one that waits for torch to import. Ingestion needs
    only the embedding model, not the LLM client.
    """
    from Services.warmup import warm_up

    warm_up(include_llm=False)
