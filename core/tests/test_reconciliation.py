"""Tests for balance-level reconciliation (account ending balance vs posted GL).
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from core.models import (
    BankStatementBalance,
    Flag,
    FlagType,
    QBAccount,
    SourceType,
    Transaction,
)
from core.reconciliation.engine import check_account_balances, run_reconciliation


def _make_txn(**overrides) -> Transaction:
    defaults = dict(
        date=dt.date(2026, 6, 15),
        vendor="Acme Corp",
        amount=Decimal("100.00"),
        category="Office Supplies",
        gl_account="Operating Checking",
        qb_transaction_id="QB-1",
        source_type=SourceType.PURCHASE,
        realm_id="realm-a",
    )
    defaults.update(overrides)
    return Transaction.objects.create(**defaults)


class CheckAccountBalancesTests(TestCase):
    def test_exact_match_creates_no_flag(self) -> None:
        _make_txn(amount=Decimal("3621.93"))
        BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("3621.93"),
            source=BankStatementBalance.Source.MANUAL,
        )
        result = check_account_balances("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 0)
        self.assertEqual(Flag.objects.filter(flag_type=FlagType.BALANCE_RECONCILIATION).count(), 0)

    def test_small_difference_within_tolerance_creates_no_flag(self) -> None:
        _make_txn(amount=Decimal("100.00"))
        BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("100.005"),
            source=BankStatementBalance.Source.MANUAL,
        )
        result = check_account_balances("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 0)

    def test_large_difference_creates_high_severity_flag(self) -> None:
        _make_txn(amount=Decimal("568.38"))
        balance = BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-3621.93"),
            source=BankStatementBalance.Source.MANUAL,
        )
        result = check_account_balances("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 1)
        flag = Flag.objects.get(flag_type=FlagType.BALANCE_RECONCILIATION)
        self.assertEqual(flag.severity, "high")
        self.assertIn("Operating Checking", flag.reason)
        self.assertIn("-3621.93", flag.reason)
        self.assertIn("568.38", flag.reason)
        self.assertEqual(flag.bank_statement_balance, balance)

    def test_missing_bank_statement_balance_skips_account(self) -> None:
        _make_txn(amount=Decimal("100.00"))
        result = check_account_balances("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 0)
        self.assertEqual(result["accounts_checked"], 0)

    def test_realm_isolation(self) -> None:
        _make_txn(realm_id="realm-a", amount=Decimal("568.38"))
        _make_txn(realm_id="realm-b", amount=Decimal("999.99"))
        BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-3621.93"),
            source=BankStatementBalance.Source.MANUAL,
        )
        result = check_account_balances("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 1)
        self.assertEqual(Flag.objects.filter(realm_id="realm-b").count(), 0)

    def test_idempotent_runs_replace_existing_balance_flag(self) -> None:
        _make_txn(amount=Decimal("568.38"))
        BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-3621.93"),
            source=BankStatementBalance.Source.MANUAL,
        )
        check_account_balances("2026-06", realm_id="realm-a")
        first_flag_id = Flag.objects.get(flag_type=FlagType.BALANCE_RECONCILIATION).id

        check_account_balances("2026-06", realm_id="realm-a")
        flags = Flag.objects.filter(flag_type=FlagType.BALANCE_RECONCILIATION)
        self.assertEqual(flags.count(), 1)
        self.assertNotEqual(flags.first().id, first_flag_id)


class RunReconciliationBalanceTests(TestCase):
    def test_balance_flag_included_in_reconciliation_summary(self) -> None:
        _make_txn(amount=Decimal("568.38"))
        BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-3621.93"),
            source=BankStatementBalance.Source.MANUAL,
        )
        result = run_reconciliation("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 1)
        self.assertEqual(Flag.objects.filter(flag_type=FlagType.BALANCE_RECONCILIATION).count(), 1)
