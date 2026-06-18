"""Celery configuration for the Monthly Close Assistant (Prompt 12).

Loads the Django settings module and creates a Celery app that auto-discovers
tasks from installed apps.
"""
from __future__ import annotations

import os

from celery import Celery

os.environ.setdefault("DJANGO_SETTINGS_MODULE", "close_assistant.settings")

app = Celery("close_assistant")
app.config_from_object("django.conf:settings", namespace="CELERY")
app.autodiscover_tasks()
