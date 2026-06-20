"""``run_connectwise_reconciliation`` management command.

Runs the ConnectWise-to-QBO reconciliation engine for a target month and realm,
then prints a summary of clients checked and flags created.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.engines import run_connectwise_reconciliation
from core.quickbooks import tokens as qb_tokens


class Command(BaseCommand):
    help = (
        "Run ConnectWise-to-QBO reconciliation for a month and print a summary."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm ID (company) to scope reconciliation to.",
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

        result = run_connectwise_reconciliation(month=month, realm_id=realm_id)

        self.stdout.write(
            self.style.SUCCESS(
                f"ConnectWise reconciliation complete for {month}:"
            )
        )
        self.stdout.write(f"  Clients checked:   {result['clients_checked']}")
        self.stdout.write(f"  Unbilled flags:    {result['unbilled_flags']}")
        self.stdout.write(f"  Margin flags:      {result['margin_flags']}")
        self.stdout.write(f"  Missing mappings:  {result['missing_mappings']}")
