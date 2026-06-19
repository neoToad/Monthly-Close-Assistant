"""``set_bank_balance`` management command.

Create or update a ``BankStatementBalance`` row so the reconciliation engine can
compare the bank's ending balance to the posted GL activity for the account/month.
"""
from __future__ import annotations

from decimal import Decimal

from django.core.management.base import BaseCommand, CommandError

from core.models import BankStatementBalance, QuickBooksCompany


class Command(BaseCommand):
    help = (
        "Set the ending bank balance for a QuickBooks account and month. "
        "Used to seed the balance-reconciliation control."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            required=True,
            help="QuickBooks realm ID (company) the account belongs to.",
        )
        parser.add_argument(
            "--account-id",
            required=True,
            help="QuickBooks account id for the cash account.",
        )
        parser.add_argument(
            "--balance",
            required=True,
            type=Decimal,
            help="Ending bank balance as a decimal (e.g. -3621.93).",
        )
        parser.add_argument(
            "--name",
            default="",
            help="Account name as shown in QuickBooks (used to match GL transactions).",
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]
        if len(month) != 7 or month[4] != "-":
            raise CommandError(f"Month must be in YYYY-MM format, got {month!r}.")

        realm_id = options["realm_id"]
        account_id = options["account_id"]
        balance = options["balance"]
        account_name = options["name"] or account_id
        company = QuickBooksCompany.objects.for_realm(realm_id)

        obj, created = BankStatementBalance.objects.update_or_create(
            company=company,
            qb_account_id=account_id,
            month=month,
            defaults={
                "realm_id": realm_id,
                "account_name": account_name,
                "ending_balance": balance,
                "source": BankStatementBalance.Source.MANUAL,
            },
        )

        action = "Created" if created else "Updated"
        self.stdout.write(
            self.style.SUCCESS(
                f"{action} bank statement balance for {account_name} "
                f"({realm_id}/{account_id}) in {month}: {balance}"
            )
        )
