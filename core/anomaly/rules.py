"""Rule-based anomaly detection for the Monthly Close Assistant (Prompt 8).

Checks a month's ``Transaction`` records for:

* Vendor amounts more than 2 standard deviations from that vendor's historical mean.
* Duplicate transactions (same vendor + amount within a 7-day window).
* New vendors with no transaction history before this month.
* Categories whose total spend changed more than 200% compared to the prior month.

Every hit creates a ``Flag`` record with ``flag_type="anomaly"``.
"""
from __future__ import annotations

import calendar
import datetime as dt
import logging
from decimal import Decimal
from typing import Optional

import pandas as pd
from django.db import transaction

from core.models import Flag, FlagType, QuickBooksCompany, Severity, Transaction

logger = logging.getLogger(__name__)

#: Minimum historical data points needed before a z-score check is meaningful.
MIN_ZSCORE_SAMPLES = 3

#: Z-score threshold for flagging a vendor amount as anomalous.
ZSCORE_THRESHOLD = 2.0

#: Window in days for duplicate detection.
DUPLICATE_WINDOW_DAYS = 7

#: Month-over-month category change threshold (e.g., 2.0 = 200%).
CATEGORY_MOM_THRESHOLD = 2.0


def _month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """Return (first_day, last_day) for a ``YYYY-MM`` string."""
    year, mon = int(month[:4]), int(month[5:7])
    first = dt.date(year, mon, 1)
    last = dt.date(year, mon, calendar.monthrange(year, mon)[1])
    return first, last


def _load_transactions_df(month: str, realm_id: Optional[str] = None) -> pd.DataFrame:
    """Load all ``Transaction`` records for ``month`` as a DataFrame."""
    first, last = _month_bounds(month)
    qs = Transaction.objects.filter(date__range=(first, last))
    if realm_id:
        qs = qs.filter(realm_id=realm_id)
    qs = qs.values("id", "date", "vendor", "amount", "category")
    df = pd.DataFrame.from_records(qs)
    if df.empty:
        return df
    df = df.copy(deep=True)
    df = df.assign(
        date=pd.to_datetime(df["date"]).dt.date,
        amount=df["amount"].apply(lambda v: Decimal(str(v))),
        vendor_lower=df["vendor"].str.lower(),
        category_lower=df["category"].str.lower(),
    )
    return df


def _vendor_zscore_anomalies(
    df: pd.DataFrame,
    month: str,
    realm_id: Optional[str] = None,
    company: Optional["QuickBooksCompany"] = None,
) -> list[Flag]:
    """Flag current-month vendor amounts > 2σ from historical average."""
    flags: list[Flag] = []
    if df.empty:
        return flags

    realm_id = realm_id or ""
    current_ids = set(df["id"])
    for vendor_lower, group in df.groupby("vendor_lower"):
        vendor_name = group["vendor"].iloc[0]
        # Historical data: all transactions for this vendor excluding current month.
        hist_qs = Transaction.objects.filter(vendor__iexact=vendor_name).exclude(
            id__in=current_ids
        )
        if realm_id:
            hist_qs = hist_qs.filter(realm_id=realm_id)
        if company:
            hist_qs = hist_qs.filter(company=company)
        hist_qs = hist_qs.values("date", "amount")
        hist = pd.DataFrame.from_records(hist_qs)
        if hist.empty or len(hist) < MIN_ZSCORE_SAMPLES:
            logger.info(
                "Skipping z-score check for vendor %r: only %s historical data point(s).",
                vendor_name, 0 if hist.empty else len(hist)
            )
            continue

        hist = hist.copy(deep=True)
        hist = hist.assign(amount=hist["amount"].apply(lambda v: float(v)))
        mean = float(hist["amount"].mean())
        std = float(hist["amount"].std(ddof=0))

        for _, row in group.iterrows():
            amount = float(row["amount"])
            if std == 0:
                # Any deviation from a constant historical average is anomalous.
                if amount != mean:
                    flags.append(
                        Flag(
                            company=company,
                            realm_id=realm_id,
                            flag_type=FlagType.ANOMALY,
                            transaction_id=int(row["id"]),
                            reason=(
                                f"Vendor {row['vendor']} amount ${row['amount']} "
                                f"is outside the historical standard deviation "
                                f"(constant average ${mean:.2f})."
                            ),
                            severity=Severity.HIGH,
                        )
                    )
                continue

            z = (amount - mean) / std
            if abs(z) > ZSCORE_THRESHOLD:
                flags.append(
                    Flag(
                        company=company,
                        realm_id=realm_id,
                        flag_type=FlagType.ANOMALY,
                        transaction_id=int(row["id"]),
                        reason=(
                            f"Vendor {row['vendor']} amount ${row['amount']} is "
                            f"{abs(z):.2f} standard deviations from the historical "
                            f"average (${mean:.2f})."
                        ),
                        severity=Severity.HIGH,
                    )
                )
    return flags


def _duplicate_anomalies(
    df: pd.DataFrame,
    realm_id: Optional[str] = None,
    company: Optional["QuickBooksCompany"] = None,
) -> list[Flag]:
    """Flag duplicate-like transactions: same vendor + amount within 7 days."""
    flags: list[Flag] = []
    if df.empty or len(df) < 2:
        return flags

    realm_id = realm_id or ""
    df = df.sort_values(["vendor_lower", "amount", "date"]).copy()
    flagged_ids: set[int] = set()

    for i, row in df.iterrows():
        tid = int(row["id"])
        if tid in flagged_ids:
            continue
        vendor = row["vendor_lower"]
        amount = row["amount"]
        date = row["date"]
        # Find other rows for the same vendor/amount within 7 days (excluding self).
        mask = (
            (df["vendor_lower"] == vendor)
            & (df["amount"] == amount)
            & (df["id"] != tid)
            & (df["date"].apply(lambda d: abs((d - date).days) <= DUPLICATE_WINDOW_DAYS))
        )
        matches = df[mask]
        if not matches.empty:
            flagged_ids.add(tid)
            for _, match in matches.iterrows():
                flagged_ids.add(int(match["id"]))
            flags.append(
                Flag(
                    company=company,
                    realm_id=realm_id,
                    flag_type=FlagType.ANOMALY,
                    transaction_id=tid,
                    reason=(
                        f"Duplicate transaction: {row['vendor']} ${amount} near "
                        f"{date} appears {len(matches) + 1} time(s) within a "
                        f"{DUPLICATE_WINDOW_DAYS}-day window."
                    ),
                    severity=Severity.MEDIUM,
                )
            )
    return flags


def _new_vendor_anomalies(
    df: pd.DataFrame,
    month: str,
    realm_id: Optional[str] = None,
    company: Optional["QuickBooksCompany"] = None,
) -> list[Flag]:
    """Flag vendors appearing for the first time in the current month."""
    flags: list[Flag] = []
    if df.empty:
        return flags

    realm_id = realm_id or ""
    current_ids = set(df["id"])
    for _, row in df.iterrows():
        hist_qs = Transaction.objects.filter(vendor__iexact=row["vendor"]).exclude(
            id__in=current_ids
        )
        if realm_id:
            hist_qs = hist_qs.filter(realm_id=realm_id)
        if company:
            hist_qs = hist_qs.filter(company=company)
        has_history = hist_qs.exists()
        if not has_history:
            flags.append(
                Flag(
                    company=company,
                    realm_id=realm_id,
                    flag_type=FlagType.ANOMALY,
                    transaction_id=int(row["id"]),
                    reason=(
                        f"New vendor: {row['vendor']} has no transaction history "
                        f"before {month}."
                    ),
                    severity=Severity.LOW,
                )
            )
    return flags


def _category_mom_anomalies(
    df: pd.DataFrame,
    month: str,
    realm_id: Optional[str] = None,
    company: Optional["QuickBooksCompany"] = None,
) -> list[Flag]:
    """Flag categories whose total spend changed > 200% month-over-month."""
    flags: list[Flag] = []
    if df.empty:
        return flags

    realm_id = realm_id or ""
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 1:
        prev_month = f"{year - 1}-12"
    else:
        prev_month = f"{year}-{mon - 1:02d}"
    first_prev, last_prev = _month_bounds(prev_month)

    current_totals = df.groupby("category_lower")["amount"].sum()
    prev_qs = Transaction.objects.filter(date__range=(first_prev, last_prev))
    if realm_id:
        prev_qs = prev_qs.filter(realm_id=realm_id)
    if company:
        prev_qs = prev_qs.filter(company=company)
    prev_qs = prev_qs.values("category", "amount")
    prev_df = pd.DataFrame.from_records(prev_qs)
    if not prev_df.empty:
        prev_df = prev_df.copy(deep=True)
        prev_df = prev_df.assign(
            amount=prev_df["amount"].apply(lambda v: Decimal(str(v))),
            category_lower=prev_df["category"].str.lower(),
        )
        prev_totals = prev_df.groupby("category_lower")["amount"].sum()
    else:
        prev_totals = pd.Series(dtype=object)

    for cat_lower, current_total in current_totals.items():
        # Skip categories that have no prior-month baseline at all.
        if cat_lower not in prev_totals.index:
            continue

        # Tie category-level flags to a representative transaction so they can be
        # scoped to a month for idempotent re-runs.
        rep_id = int(df[df["category_lower"] == cat_lower].iloc[0]["id"])

        prev_total = prev_totals[cat_lower]
        # Avoid division by zero; flag any spend in a previously-zero category.
        if prev_total == 0:
            if current_total > 0:
                flags.append(
                    Flag(
                        company=company,
                        realm_id=realm_id,
                        flag_type=FlagType.ANOMALY,
                        transaction_id=rep_id,
                        reason=(
                            f"Category {cat_lower.title()} spend jumped from $0.00 "
                            f"to ${current_total} month-over-month."
                        ),
                        severity=Severity.MEDIUM,
                    )
                )
            continue

        change_ratio = float(current_total / prev_total)
        if change_ratio > 1 + CATEGORY_MOM_THRESHOLD:
            flags.append(
                Flag(
                    company=company,
                    realm_id=realm_id,
                    flag_type=FlagType.ANOMALY,
                    transaction_id=rep_id,
                    reason=(
                        f"Category {cat_lower.title()} spend increased "
                        f"{change_ratio:.0%} month-over-month "
                        f"(${prev_total} -> ${current_total})."
                    ),
                    severity=Severity.MEDIUM,
                )
            )
        elif change_ratio < 1 / (1 + CATEGORY_MOM_THRESHOLD):
            flags.append(
                Flag(
                    company=company,
                    realm_id=realm_id,
                    flag_type=FlagType.ANOMALY,
                    transaction_id=rep_id,
                    reason=(
                        f"Category {cat_lower.title()} spend decreased "
                        f"{1 / change_ratio:.0%} month-over-month "
                        f"(${prev_total} -> ${current_total})."
                    ),
                    severity=Severity.MEDIUM,
                )
            )

    return flags


def run_anomaly_detection(month: str, realm_id: Optional[str] = None) -> dict:
    """Run anomaly detection rules for ``realm_id``/``month`` and create ``Flag`` records.

    Returns a summary dict with the total number of anomaly flags created.
    """
    realm_id = realm_id or ""
    company = QuickBooksCompany.objects.for_realm(realm_id) if realm_id else None
    df = _load_transactions_df(month, realm_id=realm_id)

    if df.empty:
        return {
            "month": month,
            "realm_id": realm_id,
            "anomaly_flags_created": 0,
            "message": "No transactions for this month; no anomaly detection run.",
        }

    flags: list[Flag] = []
    flags.extend(_vendor_zscore_anomalies(df, month, realm_id=realm_id, company=company))
    flags.extend(_duplicate_anomalies(df, realm_id=realm_id, company=company))
    flags.extend(_new_vendor_anomalies(df, month, realm_id=realm_id, company=company))
    flags.extend(_category_mom_anomalies(df, month, realm_id=realm_id, company=company))

    first, last = _month_bounds(month)
    with transaction.atomic():
        delete_qs = Flag.objects.filter(
            flag_type=FlagType.ANOMALY,
            transaction_id__in=Transaction.objects.filter(
                date__range=(first, last)
            ).values("id"),
        )
        if realm_id:
            delete_qs = delete_qs.filter(realm_id=realm_id)
        if company:
            delete_qs = delete_qs.filter(company=company)
        delete_qs.delete()
        Flag.objects.bulk_create(flags)

    logger.info(
        "run_anomaly_detection(%s, %s): created %s anomaly flag(s)",
        month,
        realm_id,
        len(flags),
    )

    return {
        "month": month,
        "realm_id": realm_id or "",
        "anomaly_flags_created": len(flags),
    }
