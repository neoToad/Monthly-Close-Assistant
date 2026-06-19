"""Reconciliation engine for the Monthly Close Assistant (Prompt 7).

Compares ``Transaction`` (GL) and ``BankTransaction`` records for a month using
Pandas. Matches are based on vendor equality, amount within $0.01, and date within
1 day. Every unmatched or mismatched pair produces a ``Flag`` record with
``flag_type="reconciliation"``.
"""
from __future__ import annotations

import calendar
import datetime as dt
import logging
from decimal import Decimal
from typing import Optional

import pandas as pd
from django.db import transaction
from django.db.models import Q

from core.models import BankTransaction, Flag, FlagType, Severity, Transaction

logger = logging.getLogger(__name__)

#: Two-sided match tolerances.
AMOUNT_TOLERANCE = Decimal("0.01")
DATE_TOLERANCE_DAYS = 1


def _month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """Return (first_day, last_day) for a ``YYYY-MM`` string."""
    year, mon = int(month[:4]), int(month[5:7])
    first = dt.date(year, mon, 1)
    last = dt.date(year, mon, calendar.monthrange(year, mon)[1])
    return first, last


def _load_dataframes(month: str, realm_id: Optional[str] = None) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load Transaction and BankTransaction QuerySets as Pandas DataFrames."""
    first, last = _month_bounds(month)

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
    """Return the index of the best candidate GL row for a bank row, or None."""
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

    # Prefer exact amount, then closest amount, then closest date.
    eligible = eligible.copy()
    eligible.loc[:, "amount_diff"] = (eligible["amount"] - bank_row["amount"]).abs()
    eligible.loc[:, "date_diff"] = (eligible["date"] - bank_row["date"]).apply(
        lambda d: abs(d.days)
    )
    best = eligible.sort_values(
        by=["amount_diff", "date_diff"], ascending=[True, True]
    ).iloc[0]
    return int(best.name)


def run_reconciliation(month: str, realm_id: Optional[str] = None) -> dict:
    """Reconcile GL ``Transaction`` and ``BankTransaction`` records for ``month``.

    Creates ``Flag`` records for:

    * Amount mismatches (bank and GL match on vendor/date but amounts differ).
    * Date mismatches (bank and GL match on vendor/amount but dates differ).
    * Bank rows with no matching GL row.
    * GL rows with no matching bank row.

    Returns a summary dict with counts.
    """
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
                    realm_id=realm_id or "",
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
                    realm_id=realm_id or "",
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
                    realm_id=realm_id or "",
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
                realm_id=realm_id or "",
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

    first, last = _month_bounds(month)
    with transaction.atomic():
        delete_qs = Flag.objects.filter(
            flag_type=FlagType.RECONCILIATION
        ).filter(
            Q(transaction__date__range=(first, last))
            | Q(bank_transaction__date__range=(first, last))
        )
        if realm_id:
            delete_qs = delete_qs.filter(realm_id=realm_id)
        delete_qs.delete()
        Flag.objects.bulk_create(flags_to_create)

    logger.info(
        "run_reconciliation(%s, realm_id=%s): created %s reconciliation flag(s)",
        month,
        realm_id,
        len(flags_to_create),
    )

    return {
        "month": month,
        "flags_created": len(flags_to_create),
        "matched_bank_rows": int(bank_df["matched"].sum()),
        "unmatched_bank_rows": int((~bank_df["matched"]).sum()),
        "unmatched_gl_rows": int((~txn_df["matched"]).sum()),
    }
