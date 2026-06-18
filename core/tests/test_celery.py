"""Tests for Celery configuration and scheduled tasks (Prompt 12).

Tests run with ``CELERY_TASK_ALWAYS_EAGER=True`` so no live Redis broker is needed
in the test suite.
"""
from __future__ import annotations

from unittest import mock

from django.test import TestCase, override_settings


class CeleryConfigTests(TestCase):
    def test_celery_app_loads_from_django_settings(self) -> None:
        from close_assistant.celery import app

        self.assertEqual(app.main, "close_assistant")
        self.assertIn("redis", app.conf.broker_url)

    def test_beat_schedule_includes_nightly_sync_quickbooks(self) -> None:
        from close_assistant.celery import app

        schedule = app.conf.beat_schedule
        self.assertIn("sync-quickbooks-nightly", schedule)
        entry = schedule["sync-quickbooks-nightly"]
        self.assertEqual(entry["task"], "core.tasks.sync_quickbooks_task")
        self.assertEqual(entry["schedule"].hour, {0})
        self.assertEqual(entry["schedule"].minute, {0})


class SyncQuickbooksTaskTests(TestCase):
    @override_settings(CELERY_TASK_ALWAYS_EAGER=True)
    def test_task_calls_sync_quickbooks_command(self) -> None:
        from core.tasks import sync_quickbooks_task

        with mock.patch("core.tasks.call_command") as mock_call:
            sync_quickbooks_task.delay()

        mock_call.assert_called_once_with("sync_quickbooks")
