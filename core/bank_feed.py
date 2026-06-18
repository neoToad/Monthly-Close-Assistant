"""Fake bank feed generator for the Monthly Close Assistant (Prompt 6).

Derives ``BankTransaction`` rows from a month's ``Transaction`` records and
deliberately introduces realistic discrepancies so the reconciliation logic can be
validated against known ground truth. All manipulation uses Pandas.
"""
from __future__ import annotations

import calendar
import datetime as dt
import logging
import random
from decimal import Decimal
from typing import Optional

import pandas as pd
from django.db import transaction

from core.models import BankTransaction, Transaction

logger = logging.getLogger(__name__)

#: Small amount deltas used to simulate fees, rounding, or FX differences.
AMOUNT_DELTAS = [Decimal("-2.50"), Decimal("-1.00"), Decimal("1.00"), Decimal("3.75")]

#: Day shifts used to simulate posting delays.
DATE_SHIFTS = [-2, -1, 1, 2]

#: Fake vendors used for bank-only (extra) transactions.
EXTRA_VENDORS = ["Bank Fee", "Interest Income", "ACH Transfer", "Wire Fee"]


def _month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """Return (first_day, last_day) for a ``YYYY-MM`` string."""
    year, mon = int(month[:4]), int(month[5:7])
    first = dt.date(year, mon, 1)
    last = dt.date(year, mon, calendar.monthrange(year, mon)[1])
    return first, last


def _txns_to_dataframe(txns: list[Transaction]) -> pd.DataFrame:
    """Build a Pandas DataFrame from Transaction QuerySet values."""
    if not txns:
        return pd.DataFrame()
    df = pd.DataFrame.from_records(
        txns.values(
            "id",
            "date",
            "vendor",
            "amount",
            "category",
            "gl_account",
            "qb_transaction_id",
            "source_type",
        )
    )
    # Work with native Python dates for date shifts; amount stays as object/Decimal.
    df = df.copy()
    df.loc[:, "date"] = pd.to_datetime(df["date"]).dt.date
    return df


def generate_bank_feed(
    month: str,
    drop_rate: float = 0.05,
    dup_rate: float = 0.03,
    amount_shift_rate: float = 0.04,
    date_shift_rate: float = 0.05,
    extra_rate: float = 0.03,
    force: bool = False,
    seed: Optional[int] = None,
) -> dict:
    """Create ``BankTransaction`` records for ``month`` from ``Transaction`` rows.

    Introduces configurable discrepancies:

    * ``drop_rate`` — fraction of GL transactions omitted from the bank feed.
    * ``dup_rate`` — fraction of remaining transactions duplicated.
    * ``amount_shift_rate`` — fraction of rows whose amount is nudged by a small delta.
    * ``date_shift_rate`` — fraction of rows whose date is shifted 1–2 days.
    * ``extra_rate`` — fraction of bank-only rows added with no matching GL transaction.

    Returns a summary dict with counts for each discrepancy type. Raises ``ValueError``
    when bank data already exists for the month unless ``force=True``.
    """
    if seed is not None:
        random.seed(seed)

    first, last = _month_bounds(month)
    txns = Transaction.objects.filter(date__range=(first, last))

    if not txns.exists():
        return {
            "month": month,
            "created": 0,
            "dropped": 0,
            "duplicated": 0,
            "amount_shifts": 0,
            "date_shifts": 0,
            "extras": 0,
            "message": "No transactions for this month; no bank feed generated.",
        }

    existing = BankTransaction.objects.filter(date__range=(first, last))
    if existing.exists() and not force:
        raise ValueError(
            "Bank transactions already exist for this month. "
            "Use --force to overwrite."
        )

    if force:
        existing.delete()

    df = _txns_to_dataframe(txns)
    original_count = len(df)

    # Drop rows.
    if drop_rate and len(df) > 0:
        drop_n = max(1, int(round(len(df) * drop_rate))) if len(df) >= 2 else 0
        drop_indices = df.sample(n=drop_n, random_state=seed).index
        df = df.drop(drop_indices)
    else:
        drop_n = 0

    # Duplicate rows.
    dup_n = 0
    if dup_rate and len(df) > 0:
        dup_n = max(1, int(round(len(df) * dup_rate))) if len(df) >= 2 else 0
        dup_rows = df.sample(n=min(dup_n, len(df)), random_state=seed).copy()
        df = pd.concat([df, dup_rows], ignore_index=True)

    # Shift amounts.
    amount_shift_n = 0
    if amount_shift_rate and len(df) > 0:
        amount_shift_n = max(1, int(round(original_count * amount_shift_rate)))
        shift_indices = df.sample(n=min(amount_shift_n, len(df)), random_state=seed).index
        df.loc[shift_indices, "amount"] = df.loc[shift_indices, "amount"].apply(
            lambda v: Decimal(str(v)) + random.choice(AMOUNT_DELTAS)
        )

    # Shift dates.
    date_shift_n = 0
    if date_shift_rate and len(df) > 0:
        date_shift_n = max(1, int(round(original_count * date_shift_rate)))
        shift_indices = df.sample(n=min(date_shift_n, len(df)), random_state=seed).index
        df.loc[shift_indices, "date"] = df.loc[shift_indices, "date"].apply(
            lambda d: d + dt.timedelta(days=random.choice(DATE_SHIFTS))
        )

    # Add bank-only (extra) rows.
    extra_n = 0
    if extra_rate:
        extra_n = max(1, int(round(original_count * extra_rate)))
        extra_rows = []
        for _ in range(extra_n):
            day = random.randint(1, calendar.monthrange(first.year, first.month)[1])
            extra_rows.append(
                {
                    "date": dt.date(first.year, first.month, day),
                    "vendor": random.choice(EXTRA_VENDORS),
                    "amount": Decimal(str(round(random.uniform(5.0, 500.0), 2))),
                    "category": "Bank Only",
                    "gl_account": "",
                    "qb_transaction_id": "",
                    "source_type": "",
                    "matched_transaction_id": None,
                }
            )
        if extra_rows:
            df = pd.concat([df, pd.DataFrame(extra_rows)], ignore_index=True)

    # Persist as BankTransaction rows.
    bank_rows = []
    for _, row in df.iterrows():
        bank_rows.append(
            BankTransaction(
                date=row["date"],
                vendor=row.get("vendor") or "",
                amount=Decimal(str(row["amount"])),
                category=row.get("category") or "",
                gl_account=row.get("gl_account") or "",
                qb_transaction_id=row.get("qb_transaction_id") or "",
                source_type=row.get("source_type") or "",
                matched_transaction_id=None,
            )
        )

    with transaction.atomic():
        BankTransaction.objects.bulk_create(bank_rows)

    created = len(bank_rows)
    logger.info(
        "generate_bank_feed(%s): created=%s dropped=%s duplicated=%s amount_shifts=%s "
        "date_shifts=%s extras=%s",
        month,
        created,
        drop_n,
        dup_n,
        amount_shift_n,
        date_shift_n,
        extra_n,
    )

    return {
        "month": month,
        "created": created,
        "dropped": drop_n,
        "duplicated": dup_n,
        "amount_shifts": amount_shift_n,
        "date_shifts": date_shift_n,
        "extras": extra_n,
    }
