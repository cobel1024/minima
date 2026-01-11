import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "minima.settings")

app = Celery("minima")

app.config_from_object("django.conf:settings", namespace="CELERY")

app.autodiscover_tasks()
