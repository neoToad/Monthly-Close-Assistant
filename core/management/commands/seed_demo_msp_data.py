"""``seed_demo_msp_data`` management command.

Seeds the local database with realistic MSP (managed service provider) financial data
for demo and reconciliation testing. All data is synthetic and lives in the app's
Postgres database; no QuickBooks sandbox writes are required.
"""
from __future__ import annotations

import calendar
import datetime as dt
import random
from decimal import Decimal
from typing import Optional

from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from core.common.dates import month_bounds
from core.engines import generate_bank_feed
from core.fixtures.msp_demo_data import (
    ACCOUNTS,
    BILL_PAYMENTS,
    BILLS,
    COMPANY_NAME,
    DEPOSITS,
    JOURNAL_ENTRIES,
    OPERATING_CHECKING_STATEMENT_BALANCE,
    PURCHASES,
    TRANSACTION_BUCKETS,
    VENDOR_CREDITS,
)
from core.models import (
    BankStatementBalance,
    BankTransaction,
    QBAccount,
    QuickBooksCompany,
    SourceType,
    Transaction,
)


def _jitter_date(year: int, month: int, day: int, seed_rng: Optional[random.Random]) -> dt.date:
    """Return a date within ``year``/``month``, optionally jittered by a few days."""
    last_day = calendar.monthrange(year, month)[1]
    if seed_rng is not None:
        day = day + seed_rng.randint(-2, 2)
    day = max(1, min(day, last_day))
    return dt.date(year, month, day)


class Command(BaseCommand):
    help = (
        "Seed the local database with realistic MSP demo data for a month. "
        "No QuickBooks sandbox writes are required."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            default="demo-msp",
            help="Synthetic QuickBooks realm id (default: demo-msp).",
        )
        parser.add_argument(
            "--force",
            action="store_true",
            help="Delete existing demo data for the realm/month and re-seed.",
        )
        parser.add_argument(
            "--include-bank-feed",
            action="store_true",
            help="Also generate synthetic BankTransaction rows for reconciliation.",
        )
        parser.add_argument(
            "--seed",
            type=int,
            default=None,
            help="Optional random seed for date jitter; amounts stay fixed.",
        )

    def _validate_month(self, month: str) -> None:
        if len(month) != 7 or month[4] != "-":
            raise CommandError(f"Month must be in YYYY-MM format, got {month!r}.")
        try:
            int(month[:4])
            int(month[5:7])
        except ValueError as exc:
            raise CommandError(f"Month must be in YYYY-MM format, got {month!r}.") from exc

    def _has_existing_data(self, month: str, realm_id: str) -> bool:
        first, last = month_bounds(month)
        return Transaction.objects.filter(
            realm_id=realm_id, date__range=(first, last)
        ).exists()

    def _delete_existing_data(self, month: str, realm_id: str) -> None:
        first, last = month_bounds(month)
        with transaction.atomic():
            Transaction.objects.filter(
                realm_id=realm_id, date__range=(first, last)
            ).delete()
            BankTransaction.objects.filter(
                realm_id=realm_id, date__range=(first, last)
            ).delete()
            BankStatementBalance.objects.filter(
                realm_id=realm_id, month=month
            ).delete()

    def _seed_accounts(self, company: QuickBooksCompany, realm_id: str) -> int:
        count = 0
        for account in ACCOUNTS:
            QBAccount.objects.update_or_create(
                company=company,
                account_id=account["account_id"],
                defaults={
                    "realm_id": realm_id,
                    "name": account["name"],
                    "account_type": account["account_type"],
                    "active": True,
                },
            )
            count += 1
        return count

    def _seed_transactions(
        self,
        company: QuickBooksCompany,
        realm_id: str,
        month: str,
        seed_rng: Optional[random.Random],
    ) -> dict[str, int]:
        first, _ = month_bounds(month)
        year, mon = first.year, first.month

        source_type_map = {
            "Deposit": SourceType.DEPOSIT,
            "Bill": SourceType.BILL,
            "Purchase": SourceType.PURCHASE,
            "JournalEntry": SourceType.JOURNAL_ENTRY,
            "BillPayment": SourceType.BILL_PAYMENT,
            "VendorCredit": SourceType.VENDOR_CREDIT,
        }

        transactions: list[Transaction] = []
        counts: dict[str, int] = {}
        index = 0
        for source_label, bucket in TRANSACTION_BUCKETS:
            source_type = source_type_map[source_label]
            for row in bucket:
                index += 1
                txn_date = _jitter_date(year, mon, row["day"], seed_rng)
                transactions.append(
                    Transaction(
                        company=company,
                        realm_id=realm_id,
                        date=txn_date,
                        vendor=row["vendor"],
                        amount=Decimal(str(row["amount"])),
                        category=row["category"],
                        gl_account=row["gl_account"],
                        qb_transaction_id=f"demo-{month}-{source_label.lower()}-{index:03d}",
                        source_type=source_type,
                    )
                )
            counts[source_label] = len(bucket)

        Transaction.objects.bulk_create(transactions)
        return counts

    def _seed_bank_statement_balance(
        self, company: QuickBooksCompany, realm_id: str, month: str
    ) -> BankStatementBalance:
        balance, _ = BankStatementBalance.objects.update_or_create(
            company=company,
            qb_account_id="1000",
            month=month,
            defaults={
                "realm_id": realm_id,
                "account_name": "Operating Checking",
                "ending_balance": OPERATING_CHECKING_STATEMENT_BALANCE,
                "source": BankStatementBalance.Source.MANUAL,
            },
        )
        return balance

    def handle(self, *args, **options) -> None:
        month = options["month"]
        realm_id = options["realm_id"]
        force = options["force"]
        include_bank_feed = options["include_bank_feed"]
        seed = options["seed"]

        self._validate_month(month)

        if not force and self._has_existing_data(month, realm_id):
            raise CommandError(
                f"Demo data already exists for {realm_id} in {month}. "
                "Use --force to re-seed."
            )

        if force:
            self._delete_existing_data(month, realm_id)

        company = QuickBooksCompany.objects.for_realm(realm_id, name=COMPANY_NAME)

        seed_rng = random.Random(seed) if seed is not None else None

        account_count = self._seed_accounts(company, realm_id)
        txn_counts = self._seed_transactions(company, realm_id, month, seed_rng)
        balance = self._seed_bank_statement_balance(company, realm_id, month)

        bank_feed_rows = 0
        bank_feed_summary = ""
        if include_bank_feed:
            feed_result = generate_bank_feed(
                month=month,
                realm_id=realm_id,
                force=True,
                seed=seed,
            )
            bank_feed_rows = feed_result["created"]
            bank_feed_summary = (
                f" ({feed_result['dropped']} dropped, {feed_result['duplicated']} duplicated, "
                f"{feed_result['amount_shifts']} amount shift, {feed_result['date_shifts']} date shift, "
                f"{feed_result['extras']} extra)"
            )

        total_transactions = sum(txn_counts.values())
        self.stdout.write(
            self.style.SUCCESS(
                f"Seeded {COMPANY_NAME} for {month}:"
            )
        )
        self.stdout.write(f"  Accounts: {account_count}")
        self.stdout.write(
            f"  Transactions: {total_transactions} "
            f"(Deposits={txn_counts['Deposit']}, Bills={txn_counts['Bill']}, "
            f"Purchases={txn_counts['Purchase']}, JournalEntry={txn_counts['JournalEntry']}, "
            f"BillPayment={txn_counts['BillPayment']}, VendorCredit={txn_counts['VendorCredit']})"
        )
        self.stdout.write(
            f"  Bank statement balance: ${balance.ending_balance} for {balance.account_name}"
        )
        self.stdout.write(
            f"  Bank feed rows: {bank_feed_rows}{bank_feed_summary}"
        )
