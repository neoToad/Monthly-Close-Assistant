"""``import_bank_feed`` management command.

Reads a bank statement CSV and creates real ``BankTransaction`` records for a month.
This is the production-oriented import path; the synthetic generator is intended
only for testing.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.engines import import_bank_feed_from_csv
from core.quickbooks import tokens as qb_tokens


class Command(BaseCommand):
    help = "Import bank transactions from a CSV statement for a month."

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm ID (company) to scope the bank feed to.",
        )
        parser.add_argument(
            "--csv",
            required=True,
            help="Path to the bank statement CSV file.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing BankTransaction records for the month.",
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
        csv_path = options["csv"]

        try:
            with open(csv_path, "r", encoding="utf-8") as csv_file:
                result = import_bank_feed_from_csv(
                    csv_file=csv_file,
                    month=month,
                    realm_id=realm_id,
                    force=options["force"],
                )
        except FileNotFoundError:
            raise CommandError(f"CSV file not found: {csv_path}")
        except ValueError as exc:
            raise CommandError(str(exc))

        self.stdout.write(
            self.style.SUCCESS(
                f"Bank feed CSV imported for {month}: {result['created']} row(s) created."
            )
        )
