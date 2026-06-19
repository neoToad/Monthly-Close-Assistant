"""Thin, mockable wrappers for creating QuickBooks adjusting entries.

These helpers build python-quickbooks objects (JournalEntry, Purchase, Deposit)
from the suggestion structures produced by ``core.agent.reconcile``. They map
account names to QB ``AccountRef`` ids via local ``QBAccount`` rows and never
hit the QuickBooks API for account lookup more than once per call.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from quickbooks import QuickBooks
from quickbooks.objects.base import Ref
from quickbooks.objects.deposit import Deposit, DepositLine, DepositLineDetail
from quickbooks.objects.journalentry import (
    JournalEntry,
    JournalEntryLine,
    JournalEntryLineDetail,
)
from quickbooks.objects.purchase import Purchase
from quickbooks.objects.detailline import AccountBasedExpenseLine
from quickbooks.objects.detailline import AccountBasedExpenseLineDetail

from core.models import QBAccount

logger = logging.getLogger(__name__)


def _make_ref(value: str, name: str = "") -> Ref:
    ref = Ref()
    ref.value = value
    ref.name = name
    return ref


def _account_refs_by_name(realm_id: str, names: set[str]) -> dict[str, Ref]:
    """Return a mapping from account name to QB AccountRef for ``realm_id``.

    Raises ``ValueError`` when any requested name does not exist in ``QBAccount``.
    """
    if not names:
        return {}
    found = {
        row.name: _make_ref(row.account_id, row.name)
        for row in QBAccount.objects.filter(realm_id=realm_id, name__in=names, active=True)
    }
    missing = names - set(found.keys())
    if missing:
        raise ValueError(f"Unknown QuickBooks account(s) for realm {realm_id}: {', '.join(sorted(missing))}")
    return found


def _account_ref_by_id(realm_id: str, account_id: str) -> Ref:
    account = QBAccount.objects.get(realm_id=realm_id, account_id=account_id, active=True)
    return _make_ref(account.account_id, account.name)


def create_journal_entry(
    qb_client: QuickBooks,
    lines: list[dict],
    txn_date: str,
    private_note: str,
    realm_id: str,
) -> dict:
    """Create a QuickBooks JournalEntry from suggestion lines.

    ``lines`` entries must contain ``account_name``, ``amount`` (signed string),
    and ``posting`` (Debit/Credit).
    """
    account_names = {line["account_name"] for line in lines}
    refs = _account_refs_by_name(realm_id, account_names)

    je = JournalEntry()
    je.TxnDate = txn_date
    je.PrivateNote = private_note
    je.Line = []
    for line in lines:
        detail = JournalEntryLineDetail()
        detail.PostingType = line["posting"]
        detail.AccountRef = refs[line["account_name"]]
        je_line = JournalEntryLine()
        je_line.Amount = abs(Decimal(str(line["amount"])))
        je_line.Description = private_note
        je_line.DetailType = "JournalEntryLineDetail"
        je_line.JournalEntryLineDetail = detail
        je.Line.append(je_line)

    je.save(qb=qb_client)
    debit_total = sum(
        (Decimal(str(line["amount"])) for line in lines if Decimal(str(line["amount"])) > 0),
        start=Decimal("0"),
    )
    return {
        "object_type": "JournalEntry",
        "id": str(getattr(je, "Id", "")),
        "amount": str(debit_total),
        "lines": [
            {
                "account_id": line.JournalEntryLineDetail.AccountRef.value,
                "posting": line.JournalEntryLineDetail.PostingType,
                "amount": str(line.Amount),
            }
            for line in je.Line
        ],
    }


def create_purchase(
    qb_client: QuickBooks,
    vendor_name: str,
    amount: Decimal,
    account_id: str,
    txn_date: str,
    category_account: str,
    realm_id: str,
    private_note: str = "",
) -> dict:
    """Create a QuickBooks Purchase (expense/cash out) from a suggestion."""
    bank_ref = _account_ref_by_id(realm_id, account_id)
    category_refs = _account_refs_by_name(realm_id, {category_account})
    category_ref = category_refs[category_account]

    purchase = Purchase()
    purchase.TxnDate = txn_date
    purchase.TotalAmt = Decimal(str(amount))
    purchase.PrivateNote = private_note
    purchase.AccountRef = bank_ref
    purchase.EntityRef = _make_ref("", vendor_name)

    detail = AccountBasedExpenseLineDetail()
    detail.AccountRef = category_ref
    line = AccountBasedExpenseLine()
    line.Amount = Decimal(str(amount))
    line.Description = private_note or vendor_name
    line.DetailType = "AccountBasedExpenseLineDetail"
    line.AccountBasedExpenseLineDetail = detail
    purchase.Line = [line]

    purchase.save(qb=qb_client)
    return {
        "object_type": "Purchase",
        "id": str(getattr(purchase, "Id", "")),
        "amount": str(amount),
        "bank_account_id": bank_ref.value,
        "category_account_id": category_ref.value,
    }


def create_deposit(
    qb_client: QuickBooks,
    amount: Decimal,
    account_id: str,
    txn_date: str,
    category_account: str,
    realm_id: str,
    private_note: str = "",
) -> dict:
    """Create a QuickBooks Deposit (income/cash in) from a suggestion."""
    bank_ref = _account_ref_by_id(realm_id, account_id)
    category_refs = _account_refs_by_name(realm_id, {category_account})
    category_ref = category_refs[category_account]

    deposit = Deposit()
    deposit.TxnDate = txn_date
    deposit.TotalAmt = Decimal(str(amount))
    deposit.PrivateNote = private_note
    deposit.DepositToAccountRef = bank_ref

    detail = DepositLineDetail()
    detail.AccountRef = category_ref
    line = DepositLine()
    line.Amount = Decimal(str(amount))
    line.Description = private_note or category_account
    line.DetailType = "DepositLineDetail"
    line.DepositLineDetail = detail
    deposit.Line = [line]

    deposit.save(qb=qb_client)
    return {
        "object_type": "Deposit",
        "id": str(getattr(deposit, "Id", "")),
        "amount": str(amount),
        "bank_account_id": bank_ref.value,
        "category_account_id": category_ref.value,
    }


def _lookup_suggestion(suggestions: list[dict], suggestion_id: str) -> dict:
    for suggestion in suggestions:
        if suggestion.get("id") == suggestion_id:
            return suggestion
    raise ValueError(f"Suggestion {suggestion_id} not found")


def apply_suggestion(
    qb_client: QuickBooks,
    suggestion: dict,
    realm_id: str,
    private_note: str = "",
) -> dict:
    """Apply a single suggestion by dispatching to the correct QB write helper."""
    suggestion_type = suggestion.get("type")
    txn_date = suggestion.get("date")
    if suggestion_type == "journal_entry":
        return create_journal_entry(
            qb_client,
            lines=suggestion["lines"],
            txn_date=txn_date,
            private_note=private_note or suggestion.get("description", ""),
            realm_id=realm_id,
        )
    if suggestion_type == "purchase":
        return create_purchase(
            qb_client,
            vendor_name=suggestion.get("vendor", "Unknown"),
            amount=Decimal(str(suggestion["amount"])),
            account_id=suggestion["account_id"],
            txn_date=txn_date,
            category_account=suggestion["lines"][1]["account_name"],
            realm_id=realm_id,
            private_note=private_note or suggestion.get("description", ""),
        )
    if suggestion_type == "deposit":
        return create_deposit(
            qb_client,
            amount=Decimal(str(suggestion["amount"])),
            account_id=suggestion["account_id"],
            txn_date=txn_date,
            category_account=suggestion["lines"][1]["account_name"],
            realm_id=realm_id,
            private_note=private_note or suggestion.get("description", ""),
        )
    raise ValueError(f"Unsupported suggestion type: {suggestion_type}")
