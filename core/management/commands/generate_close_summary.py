"""``generate_close_summary`` management command (Prompt 10).

Drafts a plain-language monthly close summary using the agent in
``core/agent/summary.py`` and stores it as a ``CloseSummary`` with status "draft".
"""
from __future__ import annotations

from django.core.management.base import BaseCommand

from core.agent.summary import draft_close_summary


class Command(BaseCommand):
    help = (
        "Generate an agent-drafted close summary for a month and save it as a "
        "CloseSummary draft."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm ID (company) to scope the close summary to.",
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]
        realm_id = options.get("realm_id")
        summary = draft_close_summary(month, realm_id=realm_id)

        self.stdout.write(
            self.style.SUCCESS(f"Close summary drafted for {summary.month} (realm {summary.realm_id})")
        )
        self.stdout.write(summary.summary_text)
