"""Tests for Django management commands beyond QuickBooks sync (Prompts 6+).

Covers the fake bank feed generator, reconciliation / anomaly runner, agent summary
command, and demo seed command.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import TestCase

from core.models import (
    BankStatementBalance,
    BankTransaction,
    Flag,
    FlagType,
    QBAccount,
    SourceType,
    Transaction,
)


def _make_txn(**overrides) -> Transaction:
    defaults = dict(
        date=dt.date(2025, 1, 15),
        vendor="Acme Corp",
        amount=Decimal("100.00"),
        category="Office Supplies",
        gl_account="5000 - Supplies",
        qb_transaction_id="QB-1",
        source_type=SourceType.PURCHASE,
        realm_id="realm-a",
    )
    defaults.update(overrides)
    return Transaction.objects.create(**defaults)


class SetBankBalanceCommandTests(TestCase):
    def test_creates_manual_bank_statement_balance(self) -> None:
        out = StringIO()
        call_command(
            "set_bank_balance",
            "2026-06",
            "--realm-id", "realm-a",
            "--account-id", "qb-acc-1",
            "--balance", "-3621.93",
            "--name", "Operating Checking",
            stdout=out,
        )
        self.assertEqual(BankStatementBalance.objects.count(), 1)
        balance = BankStatementBalance.objects.first()
        self.assertEqual(balance.realm_id, "realm-a")
        self.assertEqual(balance.qb_account_id, "qb-acc-1")
        self.assertEqual(balance.account_name, "Operating Checking")
        self.assertEqual(balance.month, "2026-06")
        self.assertEqual(balance.ending_balance, Decimal("-3621.93"))
        self.assertEqual(balance.source, "manual")
        self.assertIn("created", out.getvalue().lower())

    def test_updates_existing_balance_for_same_account_month(self) -> None:
        BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-1000.00"),
            source=BankStatementBalance.Source.MANUAL,
        )
        call_command(
            "set_bank_balance",
            "2026-06",
            "--realm-id", "realm-a",
            "--account-id", "qb-acc-1",
            "--balance", "-3621.93",
            "--name", "Operating Checking",
        )
        self.assertEqual(BankStatementBalance.objects.count(), 1)
        balance = BankStatementBalance.objects.first()
        self.assertEqual(balance.ending_balance, Decimal("-3621.93"))
        self.assertEqual(balance.source, "manual")

    def test_invalid_month_format_raises_error(self) -> None:
        from django.core.management.base import CommandError
        with self.assertRaises(CommandError):
            call_command(
                "set_bank_balance",
                "not-a-month",
                "--realm-id", "realm-a",
                "--account-id", "qb-acc-1",
                "--balance", "-3621.93",
            )


class SeedBankBalancesCommandTests(TestCase):
    def _fake_token(self, realm_id: str = "realm-a"):
        token = mock.MagicMock()
        token.realm_id = realm_id
        return token

    def test_seeds_cash_like_account_balances_from_qb(self) -> None:
        from core.quickbooks import client as qb_client
        from core.quickbooks import tokens as qb_tokens

        QBAccount.objects.create(
            realm_id="realm-a", account_id="qb-acc-1", name="Operating Checking",
            account_type="Bank",
        )

        with mock.patch.object(
            qb_tokens, "get_active_token", return_value=self._fake_token("realm-a"),
        ):
            with mock.patch.object(qb_client, "build_quickbooks_client"):
                with mock.patch.object(
                    qb_client, "fetch_account_current_balances",
                    return_value={
                        "qb-acc-1": {"name": "Operating Checking", "balance": Decimal("-3621.93"), "account_type": "Bank"},
                        "qb-acc-2": {"name": "Office Supplies", "balance": Decimal("0.00"), "account_type": "Expense"},
                    },
                ):
                    call_command(
                        "seed_bank_balances",
                        "2026-06",
                        "--realm-id", "realm-a",
                    )

        balances = BankStatementBalance.objects.filter(realm_id="realm-a", month="2026-06")
        self.assertEqual(balances.count(), 1)
        balance = balances.first()
        self.assertEqual(balance.qb_account_id, "qb-acc-1")
        self.assertEqual(balance.account_name, "Operating Checking")
        self.assertEqual(balance.ending_balance, Decimal("-3621.93"))
        self.assertEqual(balance.source, "qb_api")

    def test_force_overwrites_existing_balances(self) -> None:
        from core.quickbooks import client as qb_client
        from core.quickbooks import tokens as qb_tokens

        QBAccount.objects.create(
            realm_id="realm-a", account_id="qb-acc-1", name="Operating Checking",
            account_type="Bank",
        )
        BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Old Name",
            month="2026-06",
            ending_balance=Decimal("-1000.00"),
            source=BankStatementBalance.Source.MANUAL,
        )

        with mock.patch.object(
            qb_tokens, "get_active_token", return_value=self._fake_token("realm-a"),
        ):
            with mock.patch.object(qb_client, "build_quickbooks_client"):
                with mock.patch.object(
                    qb_client, "fetch_account_current_balances",
                    return_value={
                        "qb-acc-1": {"name": "Operating Checking", "balance": Decimal("-3621.93"), "account_type": "Bank"},
                    },
                ):
                    call_command("seed_bank_balances", "2026-06", "--realm-id", "realm-a", "--force")

        balance = BankStatementBalance.objects.get(realm_id="realm-a", qb_account_id="qb-acc-1", month="2026-06")
        self.assertEqual(balance.ending_balance, Decimal("-3621.93"))
        self.assertEqual(balance.source, "qb_api")


class GenerateBankFeedCommandTests(TestCase):
    def test_no_transactions_prints_warning(self) -> None:
        out = StringIO()
        call_command("generate_bank_feed", "2025-01", stdout=out)
        self.assertIn("no transactions", out.getvalue().lower())
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_cash_only_excludes_bill_records(self) -> None:
        _make_txn(qb_transaction_id="QB-P", source_type=SourceType.PURCHASE)
        _make_txn(qb_transaction_id="QB-B", source_type=SourceType.BILL)
        _make_txn(qb_transaction_id="QB-BP", source_type=SourceType.BILL_PAYMENT)

        call_command("generate_bank_feed", "2025-01", "--cash-only", "--drop-rate", "0")

        source_types = set(BankTransaction.objects.values_list("source_type", flat=True))
        self.assertIn(SourceType.PURCHASE, source_types)
        self.assertIn(SourceType.BILL_PAYMENT, source_types)
        self.assertNotIn(SourceType.BILL, source_types)

    def test_cash_only_includes_journal_entry_with_cash_like_account(self) -> None:
        from core.models import QBAccount

        _make_txn(
            qb_transaction_id="QB-JE-CASH",
            source_type=SourceType.JOURNAL_ENTRY,
            gl_account="Operating Checking",
        )
        QBAccount.objects.create(
            realm_id="realm-a", account_id="acc-1", name="Operating Checking",
            account_type="Bank",
        )
        _make_txn(
            qb_transaction_id="QB-JE-OTHER",
            source_type=SourceType.JOURNAL_ENTRY,
            gl_account="Depreciation Expense",
        )
        QBAccount.objects.create(
            realm_id="realm-a", account_id="acc-2", name="Depreciation Expense",
            account_type="Expense",
        )

        call_command("generate_bank_feed", "2025-01", "--cash-only")

        source_types = set(BankTransaction.objects.values_list("source_type", flat=True))
        self.assertIn(SourceType.JOURNAL_ENTRY, source_types)
        self.assertEqual(
            BankTransaction.objects.filter(source_type=SourceType.JOURNAL_ENTRY).count(), 1
        )
        bt = BankTransaction.objects.get(source_type=SourceType.JOURNAL_ENTRY)
        self.assertEqual(bt.gl_account, "Operating Checking")

    def test_cash_only_includes_journal_entry_when_qbaccount_missing(self) -> None:
        _make_txn(
            qb_transaction_id="QB-JE",
            source_type=SourceType.JOURNAL_ENTRY,
            gl_account="Some Account",
        )

        call_command("generate_bank_feed", "2025-01", "--cash-only")

        self.assertEqual(
            BankTransaction.objects.filter(source_type=SourceType.JOURNAL_ENTRY).count(), 1
        )

    def test_creates_bank_transactions_for_month(self) -> None:
        for i in range(5):
            _make_txn(
                qb_transaction_id=f"QB-{i}",
                date=dt.date(2025, 1, 10 + i),
                amount=Decimal("100.00") + i,
            )

        out = StringIO()
        call_command("generate_bank_feed", "2025-01", stdout=out)

        self.assertGreater(BankTransaction.objects.count(), 0)
        output = out.getvalue()
        self.assertIn("summary", output.lower())
        self.assertIn("dropped", output.lower())
        self.assertIn("duplicated", output.lower())
        self.assertIn("amount shifts", output.lower())
        self.assertIn("date shifts", output.lower())
        self.assertIn("extra", output.lower())

    def test_force_flag_overwrites_existing_bank_data(self) -> None:
        _make_txn(qb_transaction_id="QB-A", amount=Decimal("50.00"))
        call_command("generate_bank_feed", "2025-01")
        first_count = BankTransaction.objects.count()
        self.assertGreater(first_count, 0)

        # Without --force, a second run should abort.
        from django.core.management.base import CommandError

        out = StringIO()
        with self.assertRaises(CommandError):
            call_command("generate_bank_feed", "2025-01", stdout=out)

        # With --force, it regenerates.
        call_command("generate_bank_feed", "2025-01", "--force")
        self.assertEqual(BankTransaction.objects.count(), first_count)

    def test_preserves_other_months(self) -> None:
        _make_txn(qb_transaction_id="QB-Jan", date=dt.date(2025, 1, 10))
        _make_txn(qb_transaction_id="QB-Feb", date=dt.date(2025, 2, 10))
        call_command("generate_bank_feed", "2025-01")
        self.assertEqual(BankTransaction.objects.filter(date__month=2).count(), 0)


class RunReconciliationCommandTests(TestCase):
    def test_no_data_exits_cleanly(self) -> None:
        out = StringIO()
        call_command("run_reconciliation", "2025-01", stdout=out)
        self.assertIn("no data", out.getvalue().lower())
        self.assertEqual(Flag.objects.count(), 0)

    def test_clean_match_creates_no_flags(self) -> None:
        txn = _make_txn(qb_transaction_id="QB-1", amount=Decimal("100.00"))
        BankTransaction.objects.create(
            date=txn.date, vendor=txn.vendor, amount=txn.amount,
            qb_transaction_id=txn.qb_transaction_id,
        )
        call_command("run_reconciliation", "2025-01")
        self.assertEqual(Flag.objects.filter(flag_type=FlagType.RECONCILIATION).count(), 0)

    def test_amount_mismatch_flag(self) -> None:
        txn = _make_txn(qb_transaction_id="QB-1", amount=Decimal("100.00"))
        BankTransaction.objects.create(
            date=txn.date, vendor=txn.vendor, amount=Decimal("102.50"),
            qb_transaction_id=txn.qb_transaction_id,
        )
        call_command("run_reconciliation", "2025-01")
        flags = Flag.objects.filter(flag_type=FlagType.RECONCILIATION)
        self.assertEqual(flags.count(), 1)
        self.assertIn("$102.50", flags.first().reason)
        self.assertIn("$100.00", flags.first().reason)

    def test_date_mismatch_beyond_tolerance(self) -> None:
        """A 5-day date gap exceeds the 1-day tolerance, so both sides are unmatched."""
        txn = _make_txn(qb_transaction_id="QB-1", amount=Decimal("100.00"))
        BankTransaction.objects.create(
            date=dt.date(2025, 1, 20), vendor=txn.vendor, amount=txn.amount,
            qb_transaction_id=txn.qb_transaction_id,
        )
        call_command("run_reconciliation", "2025-01")
        flags = Flag.objects.filter(flag_type=FlagType.RECONCILIATION)
        self.assertEqual(flags.count(), 2)

    def test_date_mismatch_within_tolerance_flag(self) -> None:
        txn = _make_txn(qb_transaction_id="QB-1", amount=Decimal("100.00"))
        BankTransaction.objects.create(
            date=dt.date(2025, 1, 16), vendor=txn.vendor, amount=txn.amount,
            qb_transaction_id=txn.qb_transaction_id,
        )
        call_command("run_reconciliation", "2025-01")
        flags = Flag.objects.filter(flag_type=FlagType.RECONCILIATION)
        self.assertEqual(flags.count(), 1)
        self.assertIn("date", flags.first().reason.lower())

    def test_missing_bank_transaction_flag(self) -> None:
        _make_txn(qb_transaction_id="QB-1", amount=Decimal("100.00"))
        call_command("run_reconciliation", "2025-01")
        flags = Flag.objects.filter(flag_type=FlagType.RECONCILIATION)
        self.assertEqual(flags.count(), 1)
        self.assertIn("bank", flags.first().reason.lower())

    def test_missing_gl_transaction_flag(self) -> None:
        BankTransaction.objects.create(
            date=dt.date(2025, 1, 15), vendor="Acme Corp", amount=Decimal("100.00"),
        )
        call_command("run_reconciliation", "2025-01")
        flags = Flag.objects.filter(flag_type=FlagType.RECONCILIATION)
        self.assertEqual(flags.count(), 1)
        self.assertIn("gl", flags.first().reason.lower())

    def test_reconciliation_is_idempotent(self) -> None:
        """Re-running run_reconciliation must not duplicate reconciliation flags."""
        txn = _make_txn(qb_transaction_id="QB-1", amount=Decimal("100.00"))
        BankTransaction.objects.create(
            date=txn.date, vendor=txn.vendor, amount=Decimal("102.50"),
            qb_transaction_id=txn.qb_transaction_id,
        )
        call_command("run_reconciliation", "2025-01")
        first_count = Flag.objects.filter(flag_type=FlagType.RECONCILIATION).count()
        self.assertGreater(first_count, 0)

        call_command("run_reconciliation", "2025-01")
        second_count = Flag.objects.filter(flag_type=FlagType.RECONCILIATION).count()
        self.assertEqual(second_count, first_count)


class CloseSummaryCommandTests(TestCase):
    def test_no_data_creates_draft_summary(self) -> None:
        from unittest import mock

        from core.models import CloseSummary

        out = StringIO()
        config_values = {
            "CLOSE_SUMMARY_PROVIDER": "anthropic",
            "ANTHROPIC_API_KEY": "",
            "OPENAI_API_KEY": "",
        }
        with mock.patch(
            "core.agent.summary.config",
            side_effect=lambda key, default="": config_values.get(key, default),
        ):
            call_command("generate_close_summary", "2025-01", stdout=out)
        self.assertEqual(CloseSummary.objects.count(), 1)
        summary = CloseSummary.objects.first()
        self.assertEqual(summary.status, "draft")
        self.assertIn("2025-01", summary.summary_text)
        self.assertIn("drafted", out.getvalue().lower())

    def test_command_uses_agent_summary(self) -> None:
        from core.models import CloseSummary

        _make_txn(qb_transaction_id="QB-1", category="Software", amount=Decimal("250.00"))
        out = StringIO()
        call_command("generate_close_summary", "2025-01", stdout=out)
        self.assertEqual(CloseSummary.objects.count(), 1)
        summary = CloseSummary.objects.first()
        self.assertIn("Software", summary.summary_text)


class AnomalyDetectionCommandTests(TestCase):
    def test_no_data_exits_cleanly(self) -> None:
        out = StringIO()
        call_command("run_reconciliation", "2025-01", stdout=out)
        self.assertIn("no data", out.getvalue().lower())
        self.assertEqual(Flag.objects.filter(flag_type=FlagType.ANOMALY).count(), 0)

    def test_vendor_amount_zscore_anomaly(self) -> None:
        # Historical data for Acme in prior months.
        for i in range(5):
            _make_txn(
                qb_transaction_id=f"QB-hist-{i}",
                vendor="Acme Corp",
                amount=Decimal("100.00"),
                date=dt.date(2024, 12, 1 + i),
            )
        # This month: one normal, one way above the historical average.
        _make_txn(
            qb_transaction_id="QB-normal", vendor="Acme Corp",
            amount=Decimal("100.00"), date=dt.date(2025, 1, 10),
        )
        _make_txn(
            qb_transaction_id="QB-outlier", vendor="Acme Corp",
            amount=Decimal("500.00"), date=dt.date(2025, 1, 15),
        )
        call_command("run_reconciliation", "2025-01")
        flags = Flag.objects.filter(flag_type=FlagType.ANOMALY)
        self.assertGreaterEqual(flags.count(), 1)
        self.assertTrue(
            any("acme" in f.reason.lower() and "standard deviation" in f.reason.lower()
                for f in flags),
            f"Expected z-score anomaly reason, got: {[f.reason for f in flags]}",
        )

    def test_duplicate_within_7_day_window(self) -> None:
        _make_txn(qb_transaction_id="QB-dup-1", amount=Decimal("75.00"), date=dt.date(2025, 1, 5))
        _make_txn(qb_transaction_id="QB-dup-2", amount=Decimal("75.00"), date=dt.date(2025, 1, 7))
        call_command("run_reconciliation", "2025-01")
        flags = Flag.objects.filter(flag_type=FlagType.ANOMALY)
        self.assertGreaterEqual(flags.count(), 1)
        self.assertTrue(
            any("duplicate" in f.reason.lower() for f in flags),
            f"Expected duplicate anomaly, got: {[f.reason for f in flags]}",
        )

    def test_new_vendor_anomaly(self) -> None:
        _make_txn(qb_transaction_id="QB-new", vendor="Brand New Vendor LLC", amount=Decimal("123.45"))
        call_command("run_reconciliation", "2025-01")
        flags = Flag.objects.filter(flag_type=FlagType.ANOMALY)
        self.assertEqual(flags.count(), 1)
        self.assertIn("new vendor", flags.first().reason.lower())

    def test_category_mom_greater_than_200_percent(self) -> None:
        _make_txn(
            qb_transaction_id="QB-dec", category="Software",
            amount=Decimal("100.00"), date=dt.date(2024, 12, 15),
        )
        for i in range(4):
            _make_txn(
                qb_transaction_id=f"QB-inc-{i}", category="Software",
                amount=Decimal("100.00"), date=dt.date(2025, 1, 10 + i),
            )
        call_command("run_reconciliation", "2025-01")
        flags = Flag.objects.filter(flag_type=FlagType.ANOMALY)
        self.assertGreaterEqual(flags.count(), 1)
        self.assertTrue(
            any("software" in f.reason.lower() and "month" in f.reason.lower()
                for f in flags),
            f"Expected category MoM anomaly, got: {[f.reason for f in flags]}",
        )

    def test_insufficient_history_skips_zscore(self) -> None:
        _make_txn(qb_transaction_id="QB-1", vendor="Solo Vendor", amount=Decimal("100.00"))
        _make_txn(qb_transaction_id="QB-2", vendor="Solo Vendor", amount=Decimal("500.00"))
        call_command("run_reconciliation", "2025-01")
        z_flags = [
            f for f in Flag.objects.filter(flag_type=FlagType.ANOMALY)
            if "standard deviation" in f.reason.lower()
        ]
        self.assertEqual(len(z_flags), 0)

    def test_anomaly_detection_is_idempotent(self) -> None:
        """Re-running anomaly detection must not duplicate anomaly flags."""
        _make_txn(qb_transaction_id="QB-dup-1", amount=Decimal("75.00"), date=dt.date(2025, 1, 5))
        _make_txn(qb_transaction_id="QB-dup-2", amount=Decimal("75.00"), date=dt.date(2025, 1, 7))
        call_command("run_reconciliation", "2025-01")
        first_count = Flag.objects.filter(flag_type=FlagType.ANOMALY).count()
        self.assertGreater(first_count, 0)

        call_command("run_reconciliation", "2025-01")
        second_count = Flag.objects.filter(flag_type=FlagType.ANOMALY).count()
        self.assertEqual(second_count, first_count)
