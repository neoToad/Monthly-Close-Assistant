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

from core.models import BankTransaction, Flag, FlagType, Transaction, SourceType


def _make_txn(**overrides) -> Transaction:
    defaults = dict(
        date=dt.date(2025, 1, 15),
        vendor="Acme Corp",
        amount=Decimal("100.00"),
        category="Office Supplies",
        gl_account="5000 - Supplies",
        qb_transaction_id="QB-1",
        source_type=SourceType.PURCHASE,
    )
    defaults.update(overrides)
    return Transaction.objects.create(**defaults)


class GenerateBankFeedCommandTests(TestCase):
    def test_no_transactions_prints_warning(self) -> None:
        out = StringIO()
        call_command("generate_bank_feed", "2025-01", stdout=out)
        self.assertIn("no transactions", out.getvalue().lower())
        self.assertEqual(BankTransaction.objects.count(), 0)

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
