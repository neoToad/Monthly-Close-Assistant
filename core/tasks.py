"""Celery tasks for the Monthly Close Assistant (Prompt 12).

Tasks are thin wrappers around existing management commands so the same logic is
reused whether invoked interactively, on a schedule, or via the worker.
"""
from __future__ import annotations

from celery import shared_task
from django.core.management import call_command


@shared_task
def sync_quickbooks_task() -> None:
    """Celery task wrapper for the ``sync_quickbooks`` management command.

    Runs the QuickBooks sync idempotently (keyed on ``qb_transaction_id``) and is
    scheduled nightly by Celery beat.
    """
    call_command("sync_quickbooks")
