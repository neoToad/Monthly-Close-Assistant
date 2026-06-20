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
    QuickBooksCompany,
    SourceType,
    Transaction,
)
from core.engines.reconciliation import check_account_balances, compute_posted_total, run_reconciliation


_make_txn_counter = 0


def _make_txn(**overrides) -> Transaction:
    global _make_txn_counter
    _make_txn_counter += 1
    realm_id = overrides.get("realm_id", "realm-a")
    company = QuickBooksCompany.objects.for_realm(realm_id)
    defaults = dict(
        company=company,
        date=dt.date(2026, 6, 15),
        vendor="Acme Corp",
        amount=Decimal("100.00"),
        category="Office Supplies",
        gl_account="Operating Checking",
        qb_transaction_id=f"QB-{_make_txn_counter}",
        source_type=SourceType.PURCHASE,
        realm_id=realm_id,
    )
    defaults.update(overrides)
    defaults["company"] = company
    return Transaction.objects.create(**defaults)


def _make_bank_balance(**overrides) -> BankStatementBalance:
    realm_id = overrides.get("realm_id", "realm-a")
    company = QuickBooksCompany.objects.for_realm(realm_id)
    defaults = dict(
        company=company,
        realm_id=realm_id,
        qb_account_id="qb-acc-1",
        account_name="Operating Checking",
        month="2026-06",
        ending_balance=Decimal("0.00"),
        source=BankStatementBalance.Source.MANUAL,
    )
    defaults.update(overrides)
    defaults["company"] = company
    return BankStatementBalance.objects.create(**defaults)


class ComputePostedTotalTests(TestCase):
    def test_sums_transactions_for_account_and_month(self) -> None:
        _make_txn(amount=Decimal("100.00"))
        _make_txn(amount=Decimal("50.00"))
        _make_txn(amount=Decimal("25.00"), gl_account="Different Account")
        total = compute_posted_total("2026-06", "Operating Checking", realm_id="realm-a")
        self.assertEqual(total, Decimal("150.00"))

    def test_returns_zero_when_no_transactions(self) -> None:
        total = compute_posted_total("2026-06", "Operating Checking", realm_id="realm-a")
        self.assertEqual(total, Decimal("0.00"))

    def test_realm_isolation(self) -> None:
        _make_txn(realm_id="realm-a", amount=Decimal("100.00"))
        _make_txn(realm_id="realm-b", amount=Decimal("999.00"))
        total = compute_posted_total("2026-06", "Operating Checking", realm_id="realm-a")
        self.assertEqual(total, Decimal("100.00"))

    def test_respects_month_bounds(self) -> None:
        _make_txn(date=dt.date(2026, 5, 31), amount=Decimal("100.00"))
        _make_txn(date=dt.date(2026, 6, 1), amount=Decimal("50.00"))
        _make_txn(date=dt.date(2026, 7, 1), amount=Decimal("25.00"))
        total = compute_posted_total("2026-06", "Operating Checking", realm_id="realm-a")
        self.assertEqual(total, Decimal("50.00"))


class CheckAccountBalancesTests(TestCase):
    def test_exact_match_creates_no_flag(self) -> None:
        _make_txn(amount=Decimal("3621.93"))
        _make_bank_balance(ending_balance=Decimal("3621.93"))
        result = check_account_balances("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 0)
        self.assertEqual(Flag.objects.filter(flag_type=FlagType.BALANCE_RECONCILIATION).count(), 0)

    def test_small_difference_within_tolerance_creates_no_flag(self) -> None:
        _make_txn(amount=Decimal("100.00"))
        _make_bank_balance(ending_balance=Decimal("100.005"))
        result = check_account_balances("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 0)

    def test_large_difference_creates_high_severity_flag(self) -> None:
        _make_txn(amount=Decimal("568.38"))
        balance = _make_bank_balance(ending_balance=Decimal("-3621.93"))
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
        _make_bank_balance(realm_id="realm-a", ending_balance=Decimal("-3621.93"))
        result = check_account_balances("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 1)
        self.assertEqual(Flag.objects.filter(realm_id="realm-b").count(), 0)

    def test_idempotent_runs_replace_existing_balance_flag(self) -> None:
        _make_txn(amount=Decimal("568.38"))
        _make_bank_balance(ending_balance=Decimal("-3621.93"))
        check_account_balances("2026-06", realm_id="realm-a")
        first_flag_id = Flag.objects.get(flag_type=FlagType.BALANCE_RECONCILIATION).id

        check_account_balances("2026-06", realm_id="realm-a")
        flags = Flag.objects.filter(flag_type=FlagType.BALANCE_RECONCILIATION)
        self.assertEqual(flags.count(), 1)
        self.assertNotEqual(flags.first().id, first_flag_id)


class RunReconciliationBalanceTests(TestCase):
    def test_balance_flag_included_in_reconciliation_summary(self) -> None:
        _make_txn(amount=Decimal("568.38"))
        _make_bank_balance(ending_balance=Decimal("-3621.93"))
        result = run_reconciliation("2026-06", realm_id="realm-a")
        self.assertEqual(result["balance_flags_created"], 1)
        self.assertEqual(Flag.objects.filter(flag_type=FlagType.BALANCE_RECONCILIATION).count(), 1)
