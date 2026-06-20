"""Tests for the bank-feed CSV import engine."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import StringIO

from django.test import TestCase

from core.engines.bank_feed_import import import_bank_feed_from_csv
from core.models import BankTransaction, BankTransactionSource, QuickBooksCompany


def _company(realm_id: str = "realm-a") -> QuickBooksCompany:
    return QuickBooksCompany.objects.for_realm(realm_id)


def _csv(content: str) -> StringIO:
    return StringIO(content.strip())


class ImportBankFeedFromCsvTests(TestCase):
    def test_import_creates_rows_from_well_formed_csv(self) -> None:
        _company("realm-a")
        csv = _csv("""date,amount,vendor,category,gl_account,external_id,description
2025-01-15,125.00,Acme Corp,Office Supplies,5000 - Supplies,EXT-1,POS purchase
2025-01-20,-75.50,ACH Deposit,Customer Payment,,EXT-2,Payment received
""")
        result = import_bank_feed_from_csv(
            csv, month="2025-01", realm_id="realm-a"
        )
        self.assertEqual(result["created"], 2)
        self.assertEqual(result["month"], "2025-01")
        self.assertEqual(result["realm_id"], "realm-a")

        rows = list(BankTransaction.objects.order_by("date"))
        self.assertEqual(len(rows), 2)
        self.assertEqual(rows[0].date, dt.date(2025, 1, 15))
        self.assertEqual(rows[0].amount, Decimal("125.00"))
        self.assertEqual(rows[0].vendor, "Acme Corp")
        self.assertEqual(rows[0].category, "Office Supplies")
        self.assertEqual(rows[0].gl_account, "5000 - Supplies")
        self.assertEqual(rows[0].source, BankTransactionSource.CSV_IMPORT)

        self.assertEqual(rows[1].date, dt.date(2025, 1, 20))
        self.assertEqual(rows[1].amount, Decimal("-75.50"))
        self.assertEqual(rows[1].vendor, "ACH Deposit")
        self.assertEqual(rows[1].category, "Customer Payment")
        self.assertEqual(rows[1].gl_account, "")

    def test_import_accepts_multiple_date_formats(self) -> None:
        _company("realm-a")
        csv = _csv("""date,amount
2025-01-15,10.00
01/16/2025,20.00
17-01-2025,30.00
""")
        result = import_bank_feed_from_csv(
            csv, month="2025-01", realm_id="realm-a"
        )
        self.assertEqual(result["created"], 3)
        dates = list(
            BankTransaction.objects.order_by("date").values_list("date", flat=True)
        )
        self.assertEqual(
            dates,
            [dt.date(2025, 1, 15), dt.date(2025, 1, 16), dt.date(2025, 1, 17)],
        )

    def test_missing_required_column_raises(self) -> None:
        _company("realm-a")
        csv = _csv("""amount,vendor
100.00,Acme
""")
        with self.assertRaises(ValueError) as ctx:
            import_bank_feed_from_csv(csv, month="2025-01", realm_id="realm-a")
        self.assertIn("date", str(ctx.exception).lower())

    def test_invalid_amount_collected_and_reported(self) -> None:
        _company("realm-a")
        csv = _csv("""date,amount
2025-01-15,not-a-number
2025-01-16,
""")
        with self.assertRaises(ValueError) as ctx:
            import_bank_feed_from_csv(csv, month="2025-01", realm_id="realm-a")
        message = str(ctx.exception).lower()
        self.assertIn("amount", message)
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_invalid_date_collected_and_reported(self) -> None:
        _company("realm-a")
        csv = _csv("""date,amount
not-a-date,100.00
""")
        with self.assertRaises(ValueError) as ctx:
            import_bank_feed_from_csv(csv, month="2025-01", realm_id="realm-a")
        message = str(ctx.exception).lower()
        self.assertIn("date", message)
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_date_outside_target_month_raises(self) -> None:
        _company("realm-a")
        csv = _csv("""date,amount
2025-02-15,100.00
""")
        with self.assertRaises(ValueError) as ctx:
            import_bank_feed_from_csv(csv, month="2025-01", realm_id="realm-a")
        self.assertIn("outside", str(ctx.exception).lower())
        self.assertIn("2025-01", str(ctx.exception))

    def test_empty_csv_raises(self) -> None:
        _company("realm-a")
        csv = _csv("date,amount")
        with self.assertRaises(ValueError) as ctx:
            import_bank_feed_from_csv(csv, month="2025-01", realm_id="realm-a")
        self.assertIn("row", str(ctx.exception).lower())

    def test_existing_rows_block_without_force(self) -> None:
        company = _company("realm-a")
        BankTransaction.objects.create(
            company=company,
            realm_id="realm-a",
            date=dt.date(2025, 1, 10),
            amount=Decimal("50.00"),
            source=BankTransactionSource.MANUAL,
        )
        csv = _csv("""date,amount
2025-01-15,100.00
""")
        with self.assertRaises(ValueError) as ctx:
            import_bank_feed_from_csv(csv, month="2025-01", realm_id="realm-a")
        self.assertIn("exist", str(ctx.exception).lower())

    def test_force_replaces_existing_rows_for_month(self) -> None:
        company = _company("realm-a")
        BankTransaction.objects.create(
            company=company,
            realm_id="realm-a",
            date=dt.date(2025, 1, 10),
            amount=Decimal("50.00"),
            source=BankTransactionSource.MANUAL,
        )
        csv = _csv("""date,amount
2025-01-15,100.00
""")
        result = import_bank_feed_from_csv(
            csv, month="2025-01", realm_id="realm-a", force=True
        )
        self.assertEqual(result["created"], 1)
        rows = BankTransaction.objects.filter(realm_id="realm-a")
        self.assertEqual(rows.count(), 1)
        self.assertEqual(rows.first().date, dt.date(2025, 1, 15))
        self.assertEqual(rows.first().amount, Decimal("100.00"))
        self.assertEqual(rows.first().source, BankTransactionSource.CSV_IMPORT)

    def test_force_only_replaces_same_month(self) -> None:
        company = _company("realm-a")
        BankTransaction.objects.create(
            company=company,
            realm_id="realm-a",
            date=dt.date(2025, 2, 10),
            amount=Decimal("50.00"),
            source=BankTransactionSource.MANUAL,
        )
        csv = _csv("""date,amount
2025-01-15,100.00
""")
        result = import_bank_feed_from_csv(
            csv, month="2025-01", realm_id="realm-a", force=True
        )
        self.assertEqual(result["created"], 1)
        self.assertEqual(BankTransaction.objects.filter(realm_id="realm-a").count(), 2)

    def test_source_override(self) -> None:
        _company("realm-a")
        csv = _csv("""date,amount
2025-01-15,100.00
""")
        result = import_bank_feed_from_csv(
            csv,
            month="2025-01",
            realm_id="realm-a",
            source=BankTransactionSource.MANUAL,
        )
        self.assertEqual(result["created"], 1)
        self.assertEqual(
            BankTransaction.objects.first().source, BankTransactionSource.MANUAL
        )
