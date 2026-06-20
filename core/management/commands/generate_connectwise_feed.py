"""``generate_connectwise_feed`` management command.

Creates synthetic ConnectWise activity rows from static scenario fixtures for a target
month and realm. This is a testing-only helper that mirrors the existing bank-feed
generator.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.engines import generate_connectwise_feed
from core.quickbooks import tokens as qb_tokens


class Command(BaseCommand):
    help = (
        "(Testing only) Generate synthetic ConnectWise activity for a month "
        "from static scenario fixtures."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm ID (company) to scope the feed to.",
        )
        parser.add_argument(
            "--scenario",
            default="mixed",
            choices=[
                "hourly_leakage",
                "flat_fee_profitable",
                "flat_fee_margin_erosion",
                "flat_fee_loss",
                "missing_mapping",
                "mixed",
            ],
            help="Scenario fixture to load (default: mixed).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing ConnectWise activity for the month.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Random seed for reproducible generation.",
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

        try:
            result = generate_connectwise_feed(
                month=month,
                realm_id=realm_id,
                scenario=options["scenario"],
                force=options["force"],
                seed=options["seed"],
            )
        except ValueError as exc:
            raise CommandError(str(exc))

        self.stdout.write(
            self.style.SUCCESS(
                f"ConnectWise feed generated for {month}: scenario={result['scenario']}"
            )
        )
        self.stdout.write(f"  Companies:       {result['companies_created']} created")
        self.stdout.write(f"  Customers:       {result['customers_created']} created")
        self.stdout.write(f"  Mappings:        {result['mappings_created']} created")
        self.stdout.write(f"  Work roles:      {result['work_roles_created']} created")
        self.stdout.write(f"  Time entries:    {result['time_entries_created']} created")
        self.stdout.write(f"  Expense entries: {result['expense_entries_created']} created")
        self.stdout.write(f"  Product entries: {result['product_entries_created']} created")
