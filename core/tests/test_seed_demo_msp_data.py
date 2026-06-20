"""Tests for the ``seed_demo_msp_data`` management command.

Covers idempotency, fixture counts, balance-reconciliation integration, and
anomaly detection on the seeded demo data.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import StringIO

from django.core.management import call_command
from django.test import TestCase

from core.engines import run_anomaly_detection, run_reconciliation
from core.models import (
    BankStatementBalance,
    BankTransaction,
    Flag,
    FlagType,
    QBAccount,
    QuickBooksCompany,
    SourceType,
    Transaction,
)


class SeedDemoMSPDataCommandTests(TestCase):
    def test_creates_company_and_accounts(self) -> None:
        call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-1")

        company = QuickBooksCompany.objects.get(realm_id="msp-test-1")
        self.assertEqual(company.name, "Next Level Networks Demo")
        self.assertEqual(QBAccount.objects.filter(realm_id="msp-test-1").count(), 12)
        self.assertTrue(
            QBAccount.objects.filter(
                realm_id="msp-test-1", account_id="1000", name="Operating Checking"
            ).exists()
        )

    def test_creates_expected_transaction_counts_by_source_type(self) -> None:
        call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-2")

        counts = {
            SourceType.DEPOSIT: 5,
            SourceType.BILL: 6,
            SourceType.PURCHASE: 3,
            SourceType.JOURNAL_ENTRY: 2,
            SourceType.BILL_PAYMENT: 3,
            SourceType.VENDOR_CREDIT: 1,
        }
        for source_type, expected in counts.items():
            with self.subTest(source_type=source_type):
                actual = Transaction.objects.filter(
                    realm_id="msp-test-2", source_type=source_type
                ).count()
                self.assertEqual(actual, expected, f"Expected {expected} {source_type} rows")

        self.assertEqual(Transaction.objects.filter(realm_id="msp-test-2").count(), 20)

    def test_creates_bank_statement_balance_for_checking(self) -> None:
        call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-3")

        balance = BankStatementBalance.objects.get(
            realm_id="msp-test-3", qb_account_id="1000", month="2026-06"
        )
        self.assertEqual(balance.account_name, "Operating Checking")
        self.assertEqual(balance.ending_balance, Decimal("42315.50"))
        self.assertEqual(balance.source, BankStatementBalance.Source.MANUAL)

    def test_running_twice_without_force_raises_error(self) -> None:
        call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-4")
        with self.assertRaises(Exception):
            call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-4")

    def test_force_deletes_and_re_creates_stable_counts(self) -> None:
        call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-5")
        first_ids = set(
            Transaction.objects.filter(realm_id="msp-test-5").values_list("id", flat=True)
        )
        first_balance_id = BankStatementBalance.objects.get(
            realm_id="msp-test-5", qb_account_id="1000", month="2026-06"
        ).id

        call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-5", "--force")

        second_ids = set(
            Transaction.objects.filter(realm_id="msp-test-5").values_list("id", flat=True)
        )
        second_balance_id = BankStatementBalance.objects.get(
            realm_id="msp-test-5", qb_account_id="1000", month="2026-06"
        ).id

        self.assertEqual(
            Transaction.objects.filter(realm_id="msp-test-5").count(), 20
        )
        self.assertTrue(first_ids.isdisjoint(second_ids))
        self.assertNotEqual(first_balance_id, second_balance_id)

    def test_force_preserves_other_realms_and_months(self) -> None:
        call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-6a")
        call_command("seed_demo_msp_data", "2026-07", "--realm-id", "msp-test-6a")
        call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-6b")

        call_command(
            "seed_demo_msp_data", "2026-06", "--realm-id", "msp-test-6a", "--force"
        )

        self.assertEqual(
            Transaction.objects.filter(realm_id="msp-test-6a", date__month=7).count(), 20
        )
        self.assertEqual(
            Transaction.objects.filter(realm_id="msp-test-6b", date__month=6).count(), 20
        )

    def test_include_bank_feed_creates_bank_transactions(self) -> None:
        call_command(
            "seed_demo_msp_data",
            "2026-06",
            "--realm-id",
            "msp-test-7",
            "--include-bank-feed",
        )

        self.assertGreater(BankTransaction.objects.filter(realm_id="msp-test-7").count(), 0)
        self.assertEqual(
            set(BankTransaction.objects.filter(realm_id="msp-test-7").values_list("source", flat=True)),
            {"synthetic"},
        )

    def test_default_realm_id_is_demo_msp(self) -> None:
        call_command("seed_demo_msp_data", "2026-06")
        self.assertTrue(QuickBooksCompany.objects.filter(realm_id="demo-msp").exists())
        # Clean up so the default realm does not leak into other tests.
        QuickBooksCompany.objects.filter(realm_id="demo-msp").delete()

    def test_seed_jitters_dates_within_month(self) -> None:
        call_command(
            "seed_demo_msp_data",
            "2026-06",
            "--realm-id",
            "msp-test-8",
            "--seed",
            "123",
        )

        for txn in Transaction.objects.filter(realm_id="msp-test-8"):
            self.assertEqual(txn.date.year, 2026)
            self.assertEqual(txn.date.month, 6)

    def test_invalid_month_format_raises_error(self) -> None:
        from django.core.management.base import CommandError

        with self.assertRaises(CommandError):
            call_command("seed_demo_msp_data", "not-a-month", "--realm-id", "msp-test-9")

    def test_output_summary_includes_counts(self) -> None:
        out = StringIO()
        call_command(
            "seed_demo_msp_data",
            "2026-06",
            "--realm-id",
            "msp-test-10",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Next Level Networks Demo", output)
        self.assertIn("2026-06", output)
        self.assertIn("Accounts:", output)
        self.assertIn("Transactions:", output)
        self.assertIn("Bank statement balance:", output)
        self.assertIn("Bank feed rows:", output)


class SeedDemoMSPDataReconciliationIntegrationTests(TestCase):
    def test_balance_reconciliation_flag_is_created(self) -> None:
        call_command(
            "seed_demo_msp_data",
            "2026-06",
            "--realm-id",
            "msp-rec-1",
            "--include-bank-feed",
        )

        result = run_reconciliation("2026-06", realm_id="msp-rec-1")
        self.assertGreater(result["balance_flags_created"], 0)
        self.assertTrue(
            Flag.objects.filter(
                realm_id="msp-rec-1",
                flag_type=FlagType.BALANCE_RECONCILIATION,
            ).exists()
        )

    def test_reconciliation_flags_are_created_with_bank_feed(self) -> None:
        call_command(
            "seed_demo_msp_data",
            "2026-06",
            "--realm-id",
            "msp-rec-2",
            "--include-bank-feed",
        )

        result = run_reconciliation("2026-06", realm_id="msp-rec-2")
        self.assertGreater(result["flags_created"], 0)


class SeedDemoMSPDataAnomalyIntegrationTests(TestCase):
    def test_new_vendor_anomaly_flags_are_created(self) -> None:
        call_command("seed_demo_msp_data", "2026-06", "--realm-id", "msp-anomaly-1")

        result = run_anomaly_detection("2026-06", realm_id="msp-anomaly-1")
        self.assertGreater(result["anomaly_flags_created"], 0)
        flags = Flag.objects.filter(
            realm_id="msp-anomaly-1", flag_type=FlagType.ANOMALY
        )
        self.assertTrue(
            any("new vendor" in f.reason.lower() for f in flags),
            f"Expected new-vendor anomaly, got: {[f.reason for f in flags]}",
        )
