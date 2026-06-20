"""Reconciliation engine for the Monthly Close Assistant (Prompt 7).

Compares ``Transaction`` (GL) and ``BankTransaction`` records for a month using
Pandas. Matches are based on vendor equality, amount within $0.01, and date within
1 day. Every unmatched or mismatched pair produces a ``Flag`` record with
``flag_type="reconciliation"``.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

import pandas as pd
from django.db import transaction
from django.db.models import Q, Sum

from core.common.constants import AMOUNT_TOLERANCE, BALANCE_TOLERANCE, DATE_TOLERANCE_DAYS
from core.common.dates import month_bounds
from core.models import (
    BankStatementBalance,
    BankTransaction,
    Flag,
    FlagType,
    QuickBooksCompany,
    Severity,
    Transaction,
)

logger = logging.getLogger(__name__)


def compute_posted_total(month: str, account_name: str, realm_id: Optional[str] = None) -> Decimal:
    """Return the sum of ``Transaction.amount`` for ``account_name`` in ``month``.

    The sum is scoped by ``realm_id`` when provided and is computed with a single
    grouped aggregate query. Returns ``Decimal("0")`` when no matching transactions
    exist.
    """
    first, last = month_bounds(month)
    qs = Transaction.objects.filter(
        gl_account=account_name,
        date__range=(first, last),
    )
    if realm_id:
        qs = qs.filter(realm_id=realm_id)
    total = qs.aggregate(total=Sum("amount"))["total"]
    return total or Decimal("0")


def _load_dataframes(month: str, realm_id: Optional[str] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load Transaction and BankTransaction QuerySets as Pandas DataFrames."""
    first, last = month_bounds(month)

    txns = Transaction.objects.filter(date__range=(first, last))
    bank = BankTransaction.objects.filter(date__range=(first, last))
    if realm_id:
        txns = txns.filter(realm_id=realm_id)
        bank = bank.filter(realm_id=realm_id)

    txns = txns.values(
        "id", "date", "vendor", "amount", "category", "gl_account", "qb_transaction_id"
    )
    bank = bank.values(
        "id", "date", "vendor", "amount", "category", "gl_account", "qb_transaction_id"
    )

    def _to_df(qs, prefix: str) -> pd.DataFrame:
        """Load a QuerySet as a normalized Pandas DataFrame."""
        df = pd.DataFrame.from_records(qs)
        if df.empty:
            return pd.DataFrame(
                columns=[
                    "id", "date", "vendor", "amount", "category",
                    "gl_account", "qb_transaction_id", "matched",
                ]
            )
        df = df.copy()
        df.loc[:, "date"] = pd.to_datetime(df["date"]).dt.date
        df.loc[:, "amount"] = df["amount"].apply(lambda v: Decimal(str(v)))
        df.loc[:, "matched"] = False
        for col in ["vendor", "category", "gl_account", "qb_transaction_id"]:
            if col in df.columns:
                df.loc[:, col] = df[col].fillna("").astype(str)
        return df

    return _to_df(txns, "txn"), _to_df(bank, "bank")


def _find_best_match(
    bank_row: pd.Series,
    candidates: pd.DataFrame,
) -> Optional[int]:
    """Return the index of the best candidate GL row for a bank row, or None.

    Candidates must match the bank row vendor (case-insensitive) and fall within
    ``DATE_TOLERANCE_DAYS`` and ``AMOUNT_TOLERANCE``. Tie-breaking is:

    1. Exact amount match (difference 0 wins over any non-zero difference).
    2. Smallest absolute amount difference.
    3. Smallest absolute date difference.
    """
    if candidates.empty:
        return None

    same_vendor = candidates["vendor"].str.lower() == str(bank_row["vendor"]).lower()
    within_date = candidates["date"].apply(
        lambda d: abs((d - bank_row["date"]).days) <= DATE_TOLERANCE_DAYS
    )
    within_amount = candidates["amount"].apply(
        lambda a: abs(a - bank_row["amount"]) <= AMOUNT_TOLERANCE
    )

    eligible = candidates[same_vendor & within_date]
    if eligible.empty:
        return None

    eligible = eligible.copy()
    eligible.loc[:, "amount_diff"] = (eligible["amount"] - bank_row["amount"]).abs()
    eligible.loc[:, "date_diff"] = (eligible["date"] - bank_row["date"]).apply(
        lambda d: abs(d.days)
    )
    best = eligible.sort_values(
        by=["amount_diff", "date_diff"], ascending=[True, True]
    ).iloc[0]
    return int(best.name)


def check_account_balances(month: str, realm_id: Optional[str] = None) -> dict[str, Any]:
    """Compare stored bank statement balances to posted GL totals for ``month``.

    For every ``BankStatementBalance`` row matching ``month`` (and optional
    ``realm_id``), sum the ``Transaction.amount`` values whose ``gl_account`` matches
    the statement account name. If the absolute difference exceeds
    ``BALANCE_TOLERANCE``, create a ``BALANCE_RECONCILIATION`` ``Flag`` with severity
    ``HIGH``.

    Existing balance-reconciliation flags for the same statement balance are replaced
    so the check is idempotent.

    Returns a summary dict with ``accounts_checked`` and ``balance_flags_created``.
    """
    balances_qs = BankStatementBalance.objects.filter(month=month)
    if realm_id:
        balances_qs = balances_qs.filter(realm_id=realm_id)

    flags_to_create: list[Flag] = []
    for balance in balances_qs:
        posted_total = compute_posted_total(
            month,
            balance.account_name,
            realm_id=balance.realm_id,
        )
        difference = balance.ending_balance - posted_total

        if abs(difference) > BALANCE_TOLERANCE:
            flags_to_create.append(
                Flag(
                    company=balance.company,
                    realm_id=balance.realm_id,
                    flag_type=FlagType.BALANCE_RECONCILIATION,
                    bank_statement_balance=balance,
                    reason=(
                        f"Bank ending balance (${balance.ending_balance}) for "
                        f"\"{balance.account_name}\" in {month} does not match posted "
                        f"GL total (${posted_total}); difference ${difference}."
                    ),
                    severity=Severity.HIGH,
                )
            )

    with transaction.atomic():
        # Replace existing balance-reconciliation flags for these statement balances.
        delete_qs = Flag.objects.filter(
            flag_type=FlagType.BALANCE_RECONCILIATION,
            bank_statement_balance__in=balances_qs,
        )
        delete_qs.delete()
        Flag.objects.bulk_create(flags_to_create)

    logger.info(
        "check_account_balances(%s, %s): checked=%s balance_flags=%s",
        month,
        realm_id,
        len(balances_qs),
        len(flags_to_create),
    )

    return {
        "month": month,
        "realm_id": realm_id or "",
        "accounts_checked": len(balances_qs),
        "balance_flags_created": len(flags_to_create),
    }


def run_reconciliation(month: str, realm_id: Optional[str] = None) -> dict:
    """Reconcile GL ``Transaction`` and ``BankTransaction`` records for ``month``.

    Creates ``Flag`` records for:

    * Amount mismatches (bank and GL match on vendor/date but amounts differ).
    * Date mismatches (bank and GL match on vendor/amount but dates differ).
    * Bank rows with no matching GL row.
    * GL rows with no matching bank row.

    Returns a summary dict with counts.
    """
    realm_id = realm_id or ""
    company = QuickBooksCompany.objects.for_realm(realm_id) if realm_id else None
    txn_df, bank_df = _load_dataframes(month, realm_id=realm_id)

    if txn_df.empty and bank_df.empty:
        return {
            "month": month,
            "flags_created": 0,
            "message": "No data for this month; no reconciliation run.",
        }

    flags_to_create: list[Flag] = []

    for bank_idx, bank_row in bank_df.iterrows():
        unmatched_txns = txn_df[~txn_df["matched"]]
        match_idx = _find_best_match(bank_row, unmatched_txns)

        if match_idx is None:
            flags_to_create.append(
                Flag(
                    company=company,
                    realm_id=realm_id,
                    flag_type=FlagType.RECONCILIATION,
                    bank_transaction_id=int(bank_row["id"]),
                    reason=(
                        f"Bank transaction for {bank_row['vendor']} "
                        f"({bank_row['date']}, ${bank_row['amount']}) exists but no "
                        "matching GL transaction was found."
                    ),
                    severity=Severity.HIGH,
                )
            )
            continue

        txn_row = txn_df.loc[match_idx]
        amount_diff = bank_row["amount"] - txn_row["amount"]
        date_diff_days = abs((bank_row["date"] - txn_row["date"]).days)

        if amount_diff > AMOUNT_TOLERANCE:
            flags_to_create.append(
                Flag(
                    company=company,
                    realm_id=realm_id,
                    flag_type=FlagType.RECONCILIATION,
                    transaction_id=int(txn_row["id"]),
                    bank_transaction_id=int(bank_row["id"]),
                    reason=(
                        f"Bank shows ${bank_row['amount']} but GL shows "
                        f"${txn_row['amount']} for {bank_row['vendor']} "
                        f"({bank_row['date']})."
                    ),
                    severity=Severity.MEDIUM,
                )
            )
        elif date_diff_days > 0:
            flags_to_create.append(
                Flag(
                    company=company,
                    realm_id=realm_id,
                    flag_type=FlagType.RECONCILIATION,
                    transaction_id=int(txn_row["id"]),
                    bank_transaction_id=int(bank_row["id"]),
                    reason=(
                        f"Date mismatch for {bank_row['vendor']}: bank date is "
                        f"{bank_row['date']}, GL date is {txn_row['date']} "
                        f"(difference {date_diff_days} day(s))."
                    ),
                    severity=Severity.LOW,
                )
            )

        bank_df.at[bank_idx, "matched"] = True
        txn_df.at[match_idx, "matched"] = True

    # Any remaining unmatched GL rows are missing from the bank feed.
    for _, txn_row in txn_df[~txn_df["matched"]].iterrows():
        flags_to_create.append(
            Flag(
                company=company,
                realm_id=realm_id,
                flag_type=FlagType.RECONCILIATION,
                transaction_id=int(txn_row["id"]),
                reason=(
                    f"GL transaction for {txn_row['vendor']} ({txn_row['date']}, "
                    f"${txn_row['amount']}) exists but no matching bank transaction "
                    "was found."
                ),
                severity=Severity.HIGH,
            )
        )

    first, last = month_bounds(month)
    with transaction.atomic():
        delete_qs = Flag.objects.filter(
            flag_type=FlagType.RECONCILIATION
        ).filter(
            Q(transaction__date__range=(first, last))
            | Q(bank_transaction__date__range=(first, last))
        )
        if realm_id:
            delete_qs = delete_qs.filter(realm_id=realm_id)
        if company:
            delete_qs = delete_qs.filter(company=company)
        delete_qs.delete()
        Flag.objects.bulk_create(flags_to_create)

    logger.info(
        "run_reconciliation(%s, realm_id=%s): created %s reconciliation flag(s)",
        month,
        realm_id,
        len(flags_to_create),
    )

    balance_result = check_account_balances(month, realm_id=realm_id)

    return {
        "month": month,
        "flags_created": len(flags_to_create),
        "matched_bank_rows": int(bank_df["matched"].sum()),
        "unmatched_bank_rows": int((~bank_df["matched"]).sum()),
        "unmatched_gl_rows": int((~txn_df["matched"]).sum()),
        "accounts_checked": balance_result["accounts_checked"],
        "balance_flags_created": balance_result["balance_flags_created"],
    }
