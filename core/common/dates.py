"""Shared date helpers for month-bound calculations across the app.

All functions accept a ``YYYY-MM`` string and avoid duplicating calendar math in
engines, views, and agents.
"""
from __future__ import annotations

import calendar
import datetime as dt


def month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """Return ``(first_day, last_day)`` for a ``YYYY-MM`` string."""
    year, mon = int(month[:4]), int(month[5:7])
    first = dt.date(year, mon, 1)
    last = dt.date(year, mon, calendar.monthrange(year, mon)[1])
    return first, last


def prior_month(month: str) -> str:
    """Return the ``YYYY-MM`` string for the month before ``month``."""
    year, mon = int(month[:4]), int(month[5:7])
    if mon == 1:
        return f"{year - 1}-12"
    return f"{year}-{mon - 1:02d}"


def month_bounds_for_query(month: str) -> tuple[str, str]:
    """Return ``(start_date, end_date)`` ISO strings for a ``YYYY-MM`` month."""
    first, last = month_bounds(month)
    return first.isoformat(), last.isoformat()
