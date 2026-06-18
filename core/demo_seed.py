"""Demo data seeding for the Monthly Close Assistant (Prompt 11).

Generates realistic ``Transaction`` records with Faker, derives a deliberately
imperfect ``BankTransaction`` feed, runs reconciliation + anomaly detection, and
drafts a close summary. Safe to run repeatedly: demo transactions for the target
month are deleted and recreated, the bank feed is regenerated with ``force=True``,
flags are recomputed, and the close summary is updated in place.
"""
from __future__ import annotations

import calendar
import datetime as dt
import logging
import random
from decimal import Decimal
from typing import Optional

from django.db.models import Q

from faker import Faker

from core.models import Flag, Transaction

logger = logging.getLogger(__name__)

#: Demo vendors and categories used to populate synthetic transactions.
DEMO_VENDORS = [
    "Acme Supplies",
    "Staples",
    "Amazon Web Services",
    "Microsoft",
    "Slack",
    "Salesforce",
    "Uber",
    "Starbucks",
    "Best Buy",
    "Office Depot",
]

DEMO_CATEGORIES = [
    "Office Supplies",
    "Software",
    "Cloud Services",
    "Marketing",
    "Travel",
    "Meals",
    "Equipment",
    "Professional Services",
]

DEMO_GL_ACCOUNTS = [
    "5000 - Supplies",
    "5100 - Software",
    "5200 - Cloud Services",
    "6000 - Marketing",
    "6100 - Travel",
    "6200 - Meals",
    "7000 - Equipment",
    "8000 - Professional Services",
]


def _month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """Return (first_day, last_day) for a ``YYYY-MM`` string."""
    year, mon = int(month[:4]), int(month[5:7])
    first = dt.date(year, mon, 1)
    last = dt.date(year, mon, calendar.monthrange(year, mon)[1])
    return first, last


def _clear_flags_for_month(month: str) -> None:
    """Remove flags tied to the target month before re-seeding."""
    first, last = _month_bounds(month)
    deleted, _ = Flag.objects.filter(
        Q(transaction__date__range=(first, last))
        | Q(bank_transaction__date__range=(first, last))
    ).delete()
    logger.info("seed_demo_data(%s): cleared %s flag(s)", month, deleted)


def _clear_demo_transactions(month: str) -> None:
    """Remove previously seeded demo transactions for the month."""
    first, last = _month_bounds(month)
    deleted, _ = Transaction.objects.filter(
        date__range=(first, last),
        qb_transaction_id__startswith="DEMO-",
    ).delete()
    logger.info("seed_demo_data(%s): cleared %s demo transaction(s)", month, deleted)


def _generate_transactions(month: str, count: int, faker: Faker) -> list[Transaction]:
    """Build ``count`` synthetic ``Transaction`` records for ``month``."""
    first, last = _month_bounds(month)
    days_in_month = (last - first).days + 1

    transactions: list[Transaction] = []
    for i in range(count):
        category = random.choice(DEMO_CATEGORIES)
        gl_account = DEMO_GL_ACCOUNTS[DEMO_CATEGORIES.index(category)]
        day_offset = random.randint(0, days_in_month - 1)
        amount = Decimal(str(round(random.uniform(10.0, 1000.0), 2)))
        transactions.append(
            Transaction(
                date=first + dt.timedelta(days=day_offset),
                vendor=random.choice(DEMO_VENDORS),
                amount=amount,
                category=category,
                gl_account=gl_account,
                qb_transaction_id=f"DEMO-{i + 1:04d}",
                source_type="Purchase",
            )
        )
    return transactions


def seed_demo_data(
    month: str,
    count: int = 20,
    faker: Optional[Faker] = None,
    seed: Optional[int] = None,
) -> dict:
    """Seed demo data for ``month`` and run the full analysis pipeline.

    The pipeline is idempotent for demo rows:

    1. Delete demo transactions (``qb_transaction_id__startswith="DEMO-"``) for
       the month.
    2. Create ``count`` new synthetic ``Transaction`` records.
    3. Generate a fake bank feed for the month (``force=True``).
    4. Run reconciliation + anomaly detection.
    5. Draft a close summary for the month.

    Returns a dict with counts for each stage.
    """
    from core.agent.summary import draft_close_summary
    from core.bank_feed import generate_bank_feed
    from core.reconciliation.engine import run_reconciliation

    if faker is None:
        faker = Faker()
    if seed is None:
        seed = 42
    Faker.seed(seed)
    random.seed(seed)

    # Clear flags first so we don't leave orphaned flags after deleting demo rows.
    _clear_flags_for_month(month)
    _clear_demo_transactions(month)

    txns = _generate_transactions(month, count, faker)
    Transaction.objects.bulk_create(txns)
    created_txns = len(txns)

    feed = generate_bank_feed(month, force=True, seed=seed)
    rec = run_reconciliation(month)
    summary = draft_close_summary(month)

    return {
        "month": month,
        "transactions_created": created_txns,
        "bank_transactions_created": feed.get("created", 0),
        "reconciliation_flags_created": rec.get("flags_created", 0),
        "summary_month": summary.month,
    }
