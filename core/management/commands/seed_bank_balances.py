"""``seed_bank_balances`` management command.

Sandbox convenience: fetch current account balances from QuickBooks and write them
into ``BankStatementBalance`` rows so the balance-reconciliation check can run
without a manual statement upload.

This uses each account's live ``CurrentBalance`` value, so it is only appropriate
for sandbox companies where that value is a reasonable proxy for the month-end
balance. In production, use ``set_bank_balance`` or a statement upload instead.
"""
from __future__ import annotations

from decimal import Decimal
from typing import Optional

from django.core.management.base import BaseCommand, CommandError

from core.common.constants import CASH_LIKE_ACCOUNT_TYPES
from core.models import BankStatementBalance, QBAccount, QuickBooksCompany
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens


class Command(BaseCommand):
    help = (
        "(Sandbox convenience) Fetch current QuickBooks account balances and seed "
        "BankStatementBalance rows for cash-like accounts."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm ID to seed. If omitted, seeds all connected realms.",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Overwrite existing BankStatementBalance rows for the month.",
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]
        if len(month) != 7 or month[4] != "-":
            raise CommandError(f"Month must be in YYYY-MM format, got {month!r}.")

        realm_id = options.get("realm_id")
        tokens = self._get_tokens(realm_id)
        if not tokens:
            raise CommandError(
                "No QuickBooks token is stored. Complete the OAuth flow first."
            )

        total_created = total_updated = 0
        for token in tokens:
            created, updated = self._seed_realm(token, month, force=options["force"])
            total_created += created
            total_updated += updated

        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {month}: created={total_created}, updated={total_updated}"
            )
        )

    def _get_tokens(self, realm_id: Optional[str]) -> list:
        if realm_id:
            token = qb_tokens.get_active_token(realm_id=realm_id)
            return [token] if token else []
        return list(qb_tokens.get_active_tokens())

    def _seed_realm(self, token, month: str, *, force: bool) -> tuple[int, int]:
        realm_id = token.realm_id
        company = QuickBooksCompany.objects.for_realm(realm_id)
        qb = qb_client.build_quickbooks_client(token)

        balances = qb_client.fetch_account_current_balances(qb, qb_token=token)
        if not balances:
            self.stdout.write(
                self.style.WARNING(
                    f"No account balances returned for {realm_id}; skipping."
                )
            )
            return 0, 0

        cash_account_ids = set(
            QBAccount.objects.filter(
                company=company,
                realm_id=realm_id,
                account_type__in=CASH_LIKE_ACCOUNT_TYPES,
            ).values_list("account_id", flat=True)
        )

        created = updated = 0
        for account_id, info in balances.items():
            if account_id not in cash_account_ids:
                continue

            obj, was_created = BankStatementBalance.objects.update_or_create(
                company=company,
                qb_account_id=account_id,
                month=month,
                defaults={
                    "realm_id": realm_id,
                    "account_name": info["name"],
                    "ending_balance": Decimal(str(info["balance"])),
                    "source": BankStatementBalance.Source.QB_API,
                },
            )
            if was_created:
                created += 1
            else:
                updated += 1
                # update_or_create already updated the row; --force only affects the
                # human-readable report (we count an update either way).

        self.stdout.write(
            f"  {realm_id}: created={created}, updated={updated}"
        )
        return created, updated
