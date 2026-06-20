"""``generate_close_summary`` management command (Prompt 10).

Drafts a plain-language monthly close summary using the agent in
``core/agent/summary.py`` and stores it as a ``CloseSummary`` with status "draft".
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.services.close_summary import orchestrate_close_summary
from core.quickbooks import tokens as qb_tokens


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

    def _resolve_realm_id(self, realm_id: str | None) -> str:
        if realm_id:
            return realm_id
        token = qb_tokens.get_active_token()
        if token:
            return token.realm_id
        raise CommandError(
            "--realm-id is required when no QuickBooks token is stored."
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]
        realm_id = self._resolve_realm_id(options.get("realm_id"))
        summary = orchestrate_close_summary(
            month, realm_id=realm_id, fetch_qb_gl_totals=True
        )

        self.stdout.write(
            self.style.SUCCESS(f"Close summary drafted for {summary.month} (realm {summary.realm_id})")
        )
        self.stdout.write(summary.summary_text)
