"""Production-oriented bank-feed CSV import for the Monthly Close Assistant.

``import_bank_feed_from_csv`` reads a bank statement CSV and creates
``BankTransaction`` rows, preserving source lineage as ``BankTransactionSource.CSV_IMPORT``.
"""
from __future__ import annotations

import csv
import datetime as dt
import logging
from decimal import Decimal
from typing import TextIO

from django.db import transaction

from core.common.dates import month_bounds
from core.models import BankTransaction, BankTransactionSource, QuickBooksCompany

logger = logging.getLogger(__name__)


_DATE_FORMATS = ("%Y-%m-%d", "%m/%d/%Y", "%d-%m-%Y")


def _parse_date(value: str) -> dt.date:
    """Parse ``value`` using the supported date formats."""
    for fmt in _DATE_FORMATS:
        try:
            return dt.datetime.strptime(value.strip(), fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date '{value}'.")


def _parse_amount(value: str) -> Decimal:
    """Parse ``value`` as a decimal amount."""
    try:
        return Decimal(str(value).strip().replace(",", ""))
    except Exception as exc:
        raise ValueError(f"Cannot parse amount '{value}'.") from exc


def import_bank_feed_from_csv(
    csv_file: TextIO,
    month: str,
    realm_id: str,
    force: bool = False,
    source: str = BankTransactionSource.CSV_IMPORT,
) -> dict:
    """Read a bank statement CSV and create ``BankTransaction`` rows.

    Required CSV columns: ``date``, ``amount``
    Optional columns: ``vendor``, ``category``, ``gl_account``, ``external_id``,
    ``description``

    ``date`` must be parseable as ``YYYY-MM-DD``, ``MM/DD/YYYY``, or
    ``DD-MM-YYYY``. ``amount`` must be a valid decimal. When ``month`` is supplied,
    every row's date must fall inside that month.

    By default, raises ``ValueError`` when ``BankTransaction`` rows already exist
    for ``(company, month)``. Pass ``force=True`` to replace them.

    Returns a summary dict with ``created``, ``month``, and ``realm_id``.
    """
    first, last = month_bounds(month)
    company = QuickBooksCompany.objects.for_realm(realm_id)

    reader = csv.DictReader(csv_file)
    if reader.fieldnames is None:
        raise ValueError("CSV has no header row.")

    fieldnames = {name.strip().lower() for name in reader.fieldnames}
    required = {"date", "amount"}
    missing = required - fieldnames
    if missing:
        raise ValueError(f"Missing required CSV column(s): {', '.join(sorted(missing))}.")

    rows: list[dict] = []
    errors: list[str] = []
    for line_num, raw_row in enumerate(reader, start=2):
        if not any(raw_row.values()):
            continue
        try:
            row = {key.strip().lower(): (value or "").strip() for key, value in raw_row.items()}
            parsed_date = _parse_date(row["date"])
            parsed_amount = _parse_amount(row["amount"])
            if not (first <= parsed_date <= last):
                raise ValueError(
                    f"Date {parsed_date.isoformat()} is outside {month}."
                )
            rows.append(
                {
                    "date": parsed_date,
                    "amount": parsed_amount,
                    "vendor": row.get("vendor", ""),
                    "category": row.get("category", ""),
                    "gl_account": row.get("gl_account", ""),
                    "external_id": row.get("external_id", ""),
                    "description": row.get("description", ""),
                }
            )
        except ValueError as exc:
            errors.append(f"Row {line_num}: {exc}")

    if errors:
        raise ValueError("CSV validation failed:\n" + "\n".join(errors))

    if not rows:
        raise ValueError("CSV contains no data rows.")

    existing = BankTransaction.objects.filter(
        company=company,
        realm_id=realm_id,
        date__range=(first, last),
    )
    if existing.exists() and not force:
        raise ValueError(
            "Bank transactions already exist for this month. "
            "Use force=True to overwrite."
        )

    bank_rows = [
        BankTransaction(
            company=company,
            realm_id=realm_id,
            date=row["date"],
            amount=row["amount"],
            vendor=row["vendor"],
            category=row["category"],
            gl_account=row["gl_account"],
            qb_transaction_id="",
            source_type="",
            source=source,
            matched_transaction_id=None,
        )
        for row in rows
    ]

    with transaction.atomic():
        if force:
            existing.delete()
        BankTransaction.objects.bulk_create(bank_rows)

    logger.info(
        "import_bank_feed_from_csv(%s, %s): created=%s", month, realm_id, len(bank_rows)
    )

    return {
        "created": len(bank_rows),
        "month": month,
        "realm_id": realm_id,
    }
