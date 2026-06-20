"""Synthetic ConnectWise activity feed generator for testing.

Reads static JSON scenarios under ``core/fixtures/connectwise_scenarios/`` and creates
``ConnectWiseCompany``, ``ClientMapping``, ``QBCustomer``, ``TimeEntry``,
``ExpenseEntry``, and ``ProductEntry`` rows for a target month and realm. The generator
is deterministic and idempotent on ``(company, connectwise_entry_id)``.
"""
from __future__ import annotations

import json
import logging
import random
from decimal import Decimal
from pathlib import Path
from typing import Any, Optional

import django.core.exceptions as django_exceptions
from django.db import transaction

from core.common.dates import month_bounds
from core.models import (
    BillingModel,
    ClientMapping,
    ConnectWiseCompany,
    ConnectWiseWorkRole,
    ExpenseEntry,
    ProductEntry,
    QuickBooksCompany,
    QBCustomer,
    TimeEntry,
)

logger = logging.getLogger(__name__)

FIXTURES_DIR = Path(__file__).resolve().parent.parent / "fixtures" / "connectwise_scenarios"
VALID_SCENARIOS = {
    "hourly_leakage",
    "flat_fee_profitable",
    "flat_fee_margin_erosion",
    "flat_fee_loss",
    "missing_mapping",
    "mixed",
}


def _to_decimal(value: Any) -> Optional[Decimal]:
    """Convert a JSON string/number to Decimal, preserving None."""
    if value is None:
        return None
    return Decimal(str(value))


def _clamped_date(year: int, month: int, day: int) -> Any:
    """Return a date within the month, clamping day to the last valid day."""
    import calendar

    last_day = calendar.monthrange(year, month)[1]
    from datetime import date

    return date(year, month, min(day, last_day))


def _load_scenario(scenario: str) -> dict:
    """Load and return a scenario fixture as a dict."""
    if scenario not in VALID_SCENARIOS:
        raise ValueError(f"Unknown scenario '{scenario}'. Valid: {sorted(VALID_SCENARIOS)}")
    path = FIXTURES_DIR / f"{scenario}.json"
    if not path.exists():
        raise ValueError(f"Scenario fixture not found: {path}")
    with path.open("r", encoding="utf-8") as fh:
        return json.load(fh)


def _activity_exists(company: QuickBooksCompany, first: Any, last: Any) -> bool:
    """Return True when any ConnectWise activity rows exist for the month/company."""
    filters = {"company": company, "date__range": (first, last)}
    return (
        TimeEntry.objects.filter(**filters).exists()
        or ExpenseEntry.objects.filter(**filters).exists()
        or ProductEntry.objects.filter(**filters).exists()
    )


def _delete_month_activity(company: QuickBooksCompany, first: Any, last: Any) -> None:
    """Delete all ConnectWise activity rows for the month/company."""
    filters = {"company": company, "date__range": (first, last)}
    TimeEntry.objects.filter(**filters).delete()
    ExpenseEntry.objects.filter(**filters).delete()
    ProductEntry.objects.filter(**filters).delete()


def generate_connectwise_feed(
    month: str,
    realm_id: Optional[str] = None,
    scenario: str = "mixed",
    force: bool = False,
    seed: Optional[int] = None,
) -> dict:
    """Create synthetic ConnectWise activity for ``realm_id``/``month`` from a fixture.

    Args:
        month: ``YYYY-MM`` target month.
        realm_id: QuickBooks realm to scope the activity to. Empty string is treated as
            the default (empty-realm) company.
        scenario: One of the named scenario fixtures under
            ``core/fixtures/connectwise_scenarios/``.
        force: When True, delete existing activity for the month before generating.
        seed: Optional random seed for reproducibility.

    Returns:
        Summary dict with counts of created/updated rows.

    Raises:
        ValueError: For unknown scenario or when activity already exists and force=False.
    """
    if seed is not None:
        random.seed(seed)

    realm_id = realm_id or ""
    company = QuickBooksCompany.objects.for_realm(realm_id)
    first, last = month_bounds(month)
    fixture = _load_scenario(scenario)

    if _activity_exists(company, first, last) and not force:
        raise ValueError(
            "ConnectWise activity already exists for this month. Use --force to overwrite."
        )

    if force:
        _delete_month_activity(company, first, last)

    summary = {
        "month": month,
        "realm_id": realm_id,
        "scenario": scenario,
        "companies_created": 0,
        "companies_updated": 0,
        "mappings_created": 0,
        "mappings_updated": 0,
        "customers_created": 0,
        "customers_updated": 0,
        "work_roles_created": 0,
        "work_roles_updated": 0,
        "time_entries_created": 0,
        "expense_entries_created": 0,
        "product_entries_created": 0,
    }

    year, mon = int(month[:4]), int(month[5:7])

    # Create/update work roles.
    for role in fixture.get("work_roles", []):
        _, created = ConnectWiseWorkRole.objects.update_or_create(
            company=company,
            realm_id=realm_id,
            role_name=role["role_name"],
            defaults={"burden_rate": _to_decimal(role["burden_rate"])},
        )
        summary["work_roles_created" if created else "work_roles_updated"] += 1

    time_rows: list[TimeEntry] = []
    expense_rows: list[ExpenseEntry] = []
    product_rows: list[ProductEntry] = []

    for client in fixture.get("clients", []):
        cw_company, created = ConnectWiseCompany.objects.update_or_create(
            company=company,
            realm_id=realm_id,
            connectwise_id=client["connectwise_id"],
            defaults={"name": client["connectwise_company_name"]},
        )
        summary["companies_created" if created else "companies_updated"] += 1

        qbo_customer = None
        if client.get("qbo_customer_id"):
            qbo_customer, created = QBCustomer.objects.update_or_create(
                company=company,
                realm_id=realm_id,
                customer_id=client["qbo_customer_id"],
                defaults={
                    "name": client["qbo_customer_name"],
                    "active": True,
                },
            )
            summary["customers_created" if created else "customers_updated"] += 1

        if qbo_customer is not None:
            mapping_defaults: dict[str, Any] = {
                "billing_model": client.get("billing_model", BillingModel.HOURLY),
            }
            flat_fee = _to_decimal(client.get("flat_fee_amount"))
            if flat_fee is not None:
                mapping_defaults["flat_fee_amount"] = flat_fee
            default_rate = _to_decimal(client.get("default_burden_rate"))
            if default_rate is not None:
                mapping_defaults["default_burden_rate"] = default_rate

            try:
                mapping, created = ClientMapping.objects.update_or_create(
                    company=company,
                    realm_id=realm_id,
                    connectwise_company=cw_company,
                    defaults={
                        **mapping_defaults,
                        "qbo_customer": qbo_customer,
                    },
                )
                summary["mappings_created" if created else "mappings_updated"] += 1
            except django_exceptions.ValidationError as exc:
                raise ValueError(f"Invalid mapping for {cw_company.name}: {exc}") from exc

        for entry in client.get("time_entries", []):
            time_rows.append(
                TimeEntry(
                    company=company,
                    realm_id=realm_id,
                    connectwise_entry_id=entry["connectwise_entry_id"],
                    connectwise_company=cw_company,
                    agreement_name=entry.get("agreement_name", ""),
                    ticket_number=entry.get("ticket_number", ""),
                    technician=entry["technician"],
                    date=_clamped_date(year, mon, entry["day"]),
                    hours=_to_decimal(entry["hours"]),
                    billable_rate=_to_decimal(entry.get("billable_rate")),
                    work_role=entry.get("work_role", ""),
                    is_billable=entry.get("is_billable", True),
                )
            )

        for entry in client.get("expense_entries", []):
            expense_rows.append(
                ExpenseEntry(
                    company=company,
                    realm_id=realm_id,
                    connectwise_entry_id=entry["connectwise_entry_id"],
                    connectwise_company=cw_company,
                    agreement_name=entry.get("agreement_name", ""),
                    date=_clamped_date(year, mon, entry["day"]),
                    amount=_to_decimal(entry["amount"]),
                    description=entry.get("description", ""),
                )
            )

        for entry in client.get("product_entries", []):
            product_rows.append(
                ProductEntry(
                    company=company,
                    realm_id=realm_id,
                    connectwise_entry_id=entry["connectwise_entry_id"],
                    connectwise_company=cw_company,
                    agreement_name=entry.get("agreement_name", ""),
                    date=_clamped_date(year, mon, entry["day"]),
                    amount=_to_decimal(entry["amount"]),
                    description=entry.get("description", ""),
                )
            )

    with transaction.atomic():
        if time_rows:
            TimeEntry.objects.bulk_create(time_rows)
        if expense_rows:
            ExpenseEntry.objects.bulk_create(expense_rows)
        if product_rows:
            ProductEntry.objects.bulk_create(product_rows)

    summary["time_entries_created"] = len(time_rows)
    summary["expense_entries_created"] = len(expense_rows)
    summary["product_entries_created"] = len(product_rows)

    logger.info(
        "generate_connectwise_feed(%s, %s, %s): companies=%s+%s mappings=%s+%s "
        "time=%s expense=%s product=%s",
        month,
        realm_id,
        scenario,
        summary["companies_created"],
        summary["companies_updated"],
        summary["mappings_created"],
        summary["mappings_updated"],
        summary["time_entries_created"],
        summary["expense_entries_created"],
        summary["product_entries_created"],
    )

    return summary
