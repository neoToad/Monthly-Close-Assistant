"""Tests for QuickBooks adjusting-entry write helpers.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from core.models import QBAccount, QuickBooksCompany
from core.services.qb_writes import (
    apply_suggestion,
    create_deposit,
    create_journal_entry,
    create_purchase,
)


def _company(realm_id: str = "realm-a") -> QuickBooksCompany:
    return QuickBooksCompany.objects.for_realm(realm_id)


def _account(realm_id: str = "realm-a", account_id: str = "acc-1", name: str = "Checking",
             account_type: str = "Bank") -> QBAccount:
    return QBAccount.objects.create(
        company=_company(realm_id),
        realm_id=realm_id,
        account_id=account_id,
        name=name,
        account_type=account_type,
        active=True,
    )


class JournalEntryWriteTests(TestCase):
    def test_builds_journal_entry_with_correct_lines(self) -> None:
        checking = _account(name="Operating Checking", account_id="qb-acc-1")
        _account(name="Bank Fees", account_id="exp-1", account_type="Expense")
        qb_client = mock.MagicMock()

        with mock.patch.object(
            __import__("quickbooks.objects.journalentry", fromlist=["JournalEntry"]).JournalEntry,
            "save",
        ) as mock_save:
            result = create_journal_entry(
                qb_client,
                lines=[
                    {"account_name": "Bank Fees", "amount": "53.55", "posting": "Debit"},
                    {"account_name": "Operating Checking", "amount": "-53.55", "posting": "Credit"},
                ],
                txn_date="2026-06-30",
                private_note="Residual adjustment",
                realm_id="realm-a",
            )

        self.assertEqual(result["object_type"], "JournalEntry")
        mock_save.assert_called_once_with(qb=qb_client)
        # The line account refs point to the QB account ids.
        self.assertEqual(len(result["lines"]), 2)
        self.assertEqual(result["lines"][0]["account_id"], "exp-1")
        self.assertEqual(result["lines"][1]["account_id"], "qb-acc-1")
        self.assertEqual(result["lines"][0]["posting"], "Debit")
        self.assertEqual(result["lines"][1]["posting"], "Credit")

    def test_unknown_account_raises_value_error(self) -> None:
        _account(name="Operating Checking", account_id="qb-acc-1")
        with self.assertRaises(ValueError) as cm:
            create_journal_entry(
                mock.MagicMock(),
                lines=[
                    {"account_name": "Operating Checking", "amount": "-53.55", "posting": "Credit"},
                    {"account_name": "Unknown Account", "amount": "53.55", "posting": "Debit"},
                ],
                txn_date="2026-06-30",
                private_note="x",
                realm_id="realm-a",
            )
        self.assertIn("Unknown Account", str(cm.exception))


class PurchaseWriteTests(TestCase):
    def test_builds_purchase_with_account_refs(self) -> None:
        checking = _account(name="Operating Checking", account_id="qb-acc-1")
        _account(name="Uncategorized Expense", account_id="exp-1", account_type="Expense")
        qb_client = mock.MagicMock()

        with mock.patch.object(
            __import__("quickbooks.objects.purchase", fromlist=["Purchase"]).Purchase,
            "save",
        ) as mock_save:
            result = create_purchase(
                qb_client,
                vendor_name="ACH Transfer",
                amount=Decimal("3000.00"),
                account_id="qb-acc-1",
                txn_date="2026-06-12",
                category_account="Uncategorized Expense",
                realm_id="realm-a",
            )

        self.assertEqual(result["object_type"], "Purchase")
        self.assertEqual(result["amount"], "3000.00")
        self.assertEqual(result["bank_account_id"], "qb-acc-1")
        self.assertEqual(result["category_account_id"], "exp-1")
        mock_save.assert_called_once_with(qb=qb_client)

    def test_unknown_category_account_raises(self) -> None:
        _account(name="Operating Checking", account_id="qb-acc-1")
        with self.assertRaises(ValueError):
            create_purchase(
                mock.MagicMock(),
                vendor_name="X",
                amount=Decimal("100.00"),
                account_id="qb-acc-1",
                txn_date="2026-06-12",
                category_account="Missing",
                realm_id="realm-a",
            )


class DepositWriteTests(TestCase):
    def test_builds_deposit_with_account_refs(self) -> None:
        checking = _account(name="Operating Checking", account_id="qb-acc-1")
        _account(name="Miscellaneous Income", account_id="inc-1", account_type="Income")
        qb_client = mock.MagicMock()

        with mock.patch.object(
            __import__("quickbooks.objects.deposit", fromlist=["Deposit"]).Deposit,
            "save",
        ) as mock_save:
            result = create_deposit(
                qb_client,
                amount=Decimal("500.00"),
                account_id="qb-acc-1",
                txn_date="2026-06-12",
                category_account="Miscellaneous Income",
                realm_id="realm-a",
            )

        self.assertEqual(result["object_type"], "Deposit")
        self.assertEqual(result["bank_account_id"], "qb-acc-1")
        self.assertEqual(result["category_account_id"], "inc-1")
        mock_save.assert_called_once_with(qb=qb_client)


class ApplySuggestionTests(TestCase):
    def test_dispatches_journal_entry(self) -> None:
        _account(name="Operating Checking", account_id="qb-acc-1")
        _account(name="Bank Fees", account_id="exp-1", account_type="Expense")
        qb_client = mock.MagicMock()
        suggestion = {
            "id": "sug-2",
            "type": "journal_entry",
            "description": "Residual",
            "amount": "53.55",
            "date": "2026-06-30",
            "lines": [
                {"account_name": "Bank Fees", "amount": "53.55", "posting": "Debit"},
                {"account_name": "Operating Checking", "amount": "-53.55", "posting": "Credit"},
            ],
        }

        with mock.patch.object(
            __import__("quickbooks.objects.journalentry", fromlist=["JournalEntry"]).JournalEntry,
            "save",
        ) as mock_save:
            result = apply_suggestion(qb_client, suggestion, realm_id="realm-a")

        self.assertEqual(result["object_type"], "JournalEntry")
        self.assertTrue(mock_save.called)
