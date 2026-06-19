"""Tests for the account-level reconciliation suggestion agent.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from core.models import (
    AccountReconciliationState,
    BankStatementBalance,
    BankTransaction,
    QBAccount,
    QuickBooksCompany,
    ReconciliationStatus,
    SourceType,
    Transaction,
)


def _company(realm_id: str = "realm-a") -> QuickBooksCompany:
    return QuickBooksCompany.objects.for_realm(realm_id)


def _qb_account(realm_id: str = "realm-a", account_id: str = "qb-acc-1", name: str = "Operating Checking") -> QBAccount:
    return QBAccount.objects.create(
        company=_company(realm_id),
        realm_id=realm_id,
        account_id=account_id,
        name=name,
        account_type="Bank",
    )


def _bank_balance(realm_id: str = "realm-a", qb_account_id: str = "qb-acc-1",
                  account_name: str = "Operating Checking", month: str = "2026-06",
                  ending_balance: Decimal = Decimal("-3621.93")) -> BankStatementBalance:
    return BankStatementBalance.objects.create(
        company=_company(realm_id),
        realm_id=realm_id,
        qb_account_id=qb_account_id,
        account_name=account_name,
        month=month,
        ending_balance=ending_balance,
        source=BankStatementBalance.Source.MANUAL,
    )


def _txn(realm_id: str = "realm-a", **overrides) -> Transaction:
    company = _company(realm_id)
    defaults = dict(
        company=company,
        date=dt.date(2026, 6, 15),
        vendor="Acme",
        amount=Decimal("568.38"),
        category="Office Supplies",
        gl_account="Operating Checking",
        qb_transaction_id="QB-1",
        source_type=SourceType.PURCHASE,
        realm_id=realm_id,
    )
    defaults.update(overrides)
    return Transaction.objects.create(**defaults)


def _bank_txn(realm_id: str = "realm-a", **overrides) -> BankTransaction:
    company = _company(realm_id)
    defaults = dict(
        company=company,
        date=dt.date(2026, 6, 15),
        vendor="ACH Transfer",
        amount=Decimal("3000.00"),
        category="Bank Only",
        realm_id=realm_id,
    )
    defaults.update(overrides)
    return BankTransaction.objects.create(**defaults)


class GatherInputsTests(TestCase):
    def test_gather_includes_posted_total_and_difference(self) -> None:
        _qb_account()
        _bank_balance()
        _txn()

        from core.agent.reconcile import gather_account_inputs

        inputs = gather_account_inputs("2026-06", "realm-a", "qb-acc-1")
        self.assertEqual(inputs["posted_total"], Decimal("568.38"))
        self.assertEqual(inputs["difference"], Decimal("-4190.31"))
        self.assertEqual(inputs["account_name"], "Operating Checking")

    def test_gather_includes_unmatched_bank_rows(self) -> None:
        _qb_account()
        _bank_balance()
        _txn()
        _bank_txn()

        from core.agent.reconcile import gather_account_inputs

        inputs = gather_account_inputs("2026-06", "realm-a", "qb-acc-1")
        self.assertEqual(len(inputs["unmatched_bank"]), 1)
        self.assertEqual(inputs["unmatched_bank"][0]["vendor"], "ACH Transfer")


class DeterministicSuggestionTests(TestCase):
    def test_residual_gap_returns_journal_entry(self) -> None:
        _qb_account()
        _bank_balance(ending_balance=Decimal("100.00"))
        _txn(amount=Decimal("53.55"))

        from core.agent.reconcile import suggest_account_fixes

        result = suggest_account_fixes("2026-06", "realm-a", "qb-acc-1")
        suggestions = result["suggestions"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["type"], "journal_entry")
        self.assertEqual(suggestions[0]["amount"], "46.45")
        lines = suggestions[0]["lines"]
        self.assertEqual(len(lines), 2)
        account_names = {line["account_name"] for line in lines}
        self.assertIn("Operating Checking", account_names)
        self.assertIn("Bank Fees", account_names)

    def test_bank_only_positive_amount_creates_purchase(self) -> None:
        _qb_account()
        _bank_balance(ending_balance=Decimal("-3000.00"))
        _txn(amount=Decimal("0.00"))
        _bank_txn(amount=Decimal("3000.00"), vendor="ACH Transfer")

        from core.agent.reconcile import suggest_account_fixes

        result = suggest_account_fixes("2026-06", "realm-a", "qb-acc-1")
        suggestions = [s for s in result["suggestions"] if s["type"] == "purchase"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["amount"], "3000.00")
        self.assertEqual(suggestions[0]["vendor"], "ACH Transfer")

    def test_bank_only_negative_amount_creates_deposit(self) -> None:
        _qb_account()
        _bank_balance(ending_balance=Decimal("500.00"))
        _txn(amount=Decimal("0.00"))
        _bank_txn(amount=Decimal("-500.00"), vendor="Interest Income")

        from core.agent.reconcile import suggest_account_fixes

        result = suggest_account_fixes("2026-06", "realm-a", "qb-acc-1")
        suggestions = [s for s in result["suggestions"] if s["type"] == "deposit"]
        self.assertEqual(len(suggestions), 1)
        self.assertEqual(suggestions[0]["amount"], "500.00")

    def test_matched_differences_are_not_suggested_as_new_writes(self) -> None:
        _qb_account()
        _bank_balance(ending_balance=Decimal("100.00"))
        txn = _txn(amount=Decimal("100.00"), qb_transaction_id="QB-MATCH")
        BankTransaction.objects.create(
            company=txn.company,
            realm_id=txn.realm_id,
            date=txn.date,
            vendor=txn.vendor,
            amount=Decimal("102.00"),
            qb_transaction_id=txn.qb_transaction_id,
            matched_transaction_id=txn,
        )

        from core.agent.reconcile import suggest_account_fixes

        result = suggest_account_fixes("2026-06", "realm-a", "qb-acc-1")
        # There is no residual because statement_balance == posted_total, and the
        # amount difference is only described, not suggested as a new write.
        self.assertEqual(len(result["suggestions"]), 0)


class LLMSuggestionTests(TestCase):
    def test_llm_json_parses_into_suggestions(self) -> None:
        _qb_account()
        _bank_balance()
        _txn()

        from core.agent.reconcile import suggest_account_fixes

        fake_llm = mock.MagicMock()
        fake_llm.invoke.return_value = mock.MagicMock(content='{"suggestions": [{"id": "sug-1", "type": "journal_entry", "description": "Test", "amount": "53.55", "date": "2026-06-30", "confidence": "high", "lines": [{"account_name": "Bank Fees", "amount": "53.55", "posting": "Debit"}, {"account_name": "Operating Checking", "amount": "-53.55", "posting": "Credit"}]}]}')
        result = suggest_account_fixes("2026-06", "realm-a", "qb-acc-1", llm=fake_llm)
        self.assertEqual(len(result["suggestions"]), 1)
        self.assertEqual(result["suggestions"][0]["id"], "sug-1")
        fake_llm.invoke.assert_called_once()

    def test_invalid_llm_json_falls_back_to_deterministic(self) -> None:
        _qb_account()
        _bank_balance(ending_balance=Decimal("100.00"))
        _txn(amount=Decimal("53.55"))

        from core.agent.reconcile import suggest_account_fixes

        fake_llm = mock.MagicMock()
        fake_llm.invoke.return_value = mock.MagicMock(content="not json")
        result = suggest_account_fixes("2026-06", "realm-a", "qb-acc-1", llm=fake_llm)
        self.assertTrue(any(s["type"] == "journal_entry" for s in result["suggestions"]))


class StatePersistenceTests(TestCase):
    def test_suggestions_are_cached_in_reconciliation_state(self) -> None:
        _qb_account()
        _bank_balance(ending_balance=Decimal("100.00"))
        _txn(amount=Decimal("53.55"))

        from core.agent.reconcile import suggest_account_fixes

        suggest_account_fixes("2026-06", "realm-a", "qb-acc-1")
        state = AccountReconciliationState.objects.get(
            company__realm_id="realm-a",
            qb_account_id="qb-acc-1",
            month="2026-06",
        )
        self.assertEqual(state.status, ReconciliationStatus.IN_PROGRESS)
        self.assertIn("suggestions", state.last_suggestions)
        self.assertEqual(len(state.last_suggestions["suggestions"]), 1)
