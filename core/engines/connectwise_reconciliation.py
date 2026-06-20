"""ConnectWise-to-QBO reconciliation engine.

Compares synthetic ConnectWise activity (time, expenses, products) to QuickBooks
Online invoices per client and month. Creates ``Flag`` records for unbilled
leakage on hourly/retainer clients, margin erosion on flat-fee clients, and
missing ConnectWise-to-QBO mappings.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Optional

from django.conf import settings
from django.db import transaction
from django.db.models import Sum

from core.common.constants import (
    CONNECTWISE_DEFAULT_BURDEN_RATE,
    CONNECTWISE_MARGIN_CRITICAL,
    CONNECTWISE_MARGIN_WARN,
    CONNECTWISE_TARGET_MARGIN,
    CONNECTWISE_UNBILLED_THRESHOLD,
)
from core.common.dates import month_bounds
from core.models import (
    BillingModel,
    ClientMapping,
    ConnectWiseCompany,
    ConnectWiseWorkRole,
    ExpenseEntry,
    Flag,
    FlagType,
    Invoice,
    ProductEntry,
    QuickBooksCompany,
    Severity,
    TimeEntry,
)

logger = logging.getLogger(__name__)


def _default_burden_rate() -> Decimal:
    """Return the global default burden rate from settings or constants."""
    value = getattr(settings, "CONNECTWISE_DEFAULT_BURDEN_RATE", CONNECTWISE_DEFAULT_BURDEN_RATE)
    return Decimal(str(value))


def _get_burden_rate(
    company: QuickBooksCompany,
    realm_id: str,
    role_name: str,
    client_default: Optional[Decimal],
) -> Decimal:
    """Resolve the burden rate for a time entry.

    Priority:
    1. Role-specific ``ConnectWiseWorkRole.burden_rate``.
    2. ``ClientMapping.default_burden_rate`` for the client.
    3. Global default from settings/constants.
    """
    if role_name:
        try:
            role = ConnectWiseWorkRole.objects.get(
                company=company, realm_id=realm_id, role_name=role_name
            )
            return role.burden_rate
        except ConnectWiseWorkRole.DoesNotExist:
            pass
    if client_default is not None:
        return client_default
    return _default_burden_rate()


def _qbo_invoiced_for_customer(
    company: QuickBooksCompany,
    realm_id: str,
    customer_id: str,
    first: "dt.date",
    last: "dt.date",
) -> Decimal:
    """Return the total QBO invoice amount for a customer in the month."""
    total = (
        Invoice.objects.filter(
            company=company,
            realm_id=realm_id,
            customer__customer_id=customer_id,
            invoice_date__range=(first, last),
        ).aggregate(total=Sum("total_amount"))["total"]
        or Decimal("0")
    )
    return Decimal(str(total))


def _client_activity(
    company: QuickBooksCompany,
    realm_id: str,
    cw_company: ConnectWiseCompany,
    first: "dt.date",
    last: "dt.date",
) -> tuple[Decimal, Decimal, Decimal, Decimal, Decimal]:
    """Return activity totals for a ConnectWise company in the month.

    Returns ``(billable, cost, labor_cost, expense_cost, product_cost)``.
    ``billable`` uses billable rate for hourly/retainer clients. ``cost`` uses
    burden rate for flat-fee clients. Both include expenses and products.
    """
    time_qs = TimeEntry.objects.filter(
        company=company,
        realm_id=realm_id,
        connectwise_company=cw_company,
        date__range=(first, last),
    )
    expense_qs = ExpenseEntry.objects.filter(
        company=company,
        realm_id=realm_id,
        connectwise_company=cw_company,
        date__range=(first, last),
    )
    product_qs = ProductEntry.objects.filter(
        company=company,
        realm_id=realm_id,
        connectwise_company=cw_company,
        date__range=(first, last),
    )

    mapping: Optional[ClientMapping] = None
    try:
        mapping = cw_company.client_mapping.get()
    except ClientMapping.DoesNotExist:
        pass

    client_default_rate = mapping.default_burden_rate if mapping else None

    billable = Decimal("0")
    labor_cost = Decimal("0")
    for entry in time_qs:
        burden_rate = _get_burden_rate(company, realm_id, entry.work_role, client_default_rate)
        labor_cost += entry.hours * burden_rate
        rate = entry.billable_rate or Decimal("0")
        if entry.is_billable and rate:
            billable += entry.hours * rate

    expense_cost = Decimal("0")
    for entry in expense_qs:
        expense_cost += entry.amount

    product_cost = Decimal("0")
    for entry in product_qs:
        product_cost += entry.amount

    cost = labor_cost + expense_cost + product_cost
    billable = billable + expense_cost + product_cost
    return billable, cost, labor_cost, expense_cost, product_cost


def _margin_severity(margin_percent: Decimal) -> Severity:
    """Return severity based on margin percent thresholds."""
    if margin_percent <= CONNECTWISE_MARGIN_CRITICAL:
        return Severity.HIGH
    if margin_percent < CONNECTWISE_MARGIN_WARN:
        return Severity.MEDIUM
    if margin_percent < CONNECTWISE_TARGET_MARGIN:
        return Severity.LOW
    return None  # type: ignore[return-value]


def _unbilled_severity(leakage: Decimal) -> Severity:
    """Return severity for unbilled leakage."""
    if leakage > CONNECTWISE_UNBILLED_THRESHOLD * 2:
        return Severity.HIGH
    return Severity.MEDIUM


def run_connectwise_reconciliation(month: str, realm_id: Optional[str] = None) -> dict:
    """Compare ConnectWise activity to QBO invoices per client/month.

    Creates flags for:
    - Unbilled time/expenses/products (hourly/retainer clients)
    - Margin erosion or loss (flat-fee clients)
    - Missing ClientMapping

    Prior ConnectWise flags for the realm are replaced so the run is idempotent.

    Returns a summary dict with ``clients_checked``, ``unbilled_flags``,
    ``margin_flags``, and ``missing_mappings``.
    """
    import datetime as dt

    realm_id = realm_id or ""
    company = QuickBooksCompany.objects.for_realm(realm_id)
    first, last = month_bounds(month)

    flags_to_create: list[Flag] = []
    clients_checked = 0
    unbilled_flags = 0
    margin_flags = 0
    missing_mappings = 0

    cw_companies = ConnectWiseCompany.objects.filter(company=company, realm_id=realm_id)

    for cw_company in cw_companies:
        clients_checked += 1

        mapping: Optional[ClientMapping] = None
        try:
            mapping = cw_company.client_mapping.get()
        except ClientMapping.DoesNotExist:
            pass

        if mapping is None:
            missing_mappings += 1
            flags_to_create.append(
                Flag(
                    company=company,
                    realm_id=realm_id,
                    flag_type=FlagType.CONNECTWISE_MISSING_MAPPING,
                    reason=(
                        f"{cw_company.name}: ConnectWise company has no "
                        "mapping to a QuickBooks Online customer."
                    ),
                    severity=Severity.MEDIUM,
                )
            )
            continue

        billable, cost, labor_cost, expense_cost, product_cost = _client_activity(
            company, realm_id, cw_company, first, last
        )

        if mapping.billing_model in (BillingModel.HOURLY, BillingModel.RETAINER):
            qbo_invoiced = _qbo_invoiced_for_customer(
                company, realm_id, mapping.qbo_customer.customer_id, first, last
            )
            leakage = billable - qbo_invoiced
            if leakage > CONNECTWISE_UNBILLED_THRESHOLD:
                unbilled_flags += 1
                severity = _unbilled_severity(leakage)
                flags_to_create.append(
                    Flag(
                        company=company,
                        realm_id=realm_id,
                        flag_type=FlagType.CONNECTWISE_UNBILLED,
                        reason=(
                            f"{cw_company.name} (hourly): ConnectWise billable ${billable}; "
                            f"QBO invoiced ${qbo_invoiced}. Unbilled leakage ${leakage}."
                        ),
                        severity=severity,
                    )
                )

        elif mapping.billing_model == BillingModel.FLAT_FEE:
            revenue = mapping.flat_fee_amount
            if revenue is None or revenue == Decimal("0"):
                logger.warning(
                    "Flat-fee mapping for %s has no flat_fee_amount; skipping margin check.",
                    cw_company.name,
                )
                continue

            margin_dollars = revenue - cost
            margin_percent = margin_dollars / revenue
            severity = _margin_severity(margin_percent)
            if severity is not None:
                margin_flags += 1
                flags_to_create.append(
                    Flag(
                        company=company,
                        realm_id=realm_id,
                        flag_type=FlagType.CONNECTWISE_MARGIN,
                        reason=(
                            f"{cw_company.name} (flat-fee, MRR ${revenue}): "
                            f"cost-to-serve ${cost} = labor ${labor_cost} + "
                            f"expenses ${expense_cost} + products ${product_cost}. "
                            f"Margin ${margin_dollars} ({margin_percent:.0%}) "
                            f"below {CONNECTWISE_TARGET_MARGIN:.0%} target threshold."
                        ),
                        severity=severity,
                    )
                )

    with transaction.atomic():
        Flag.objects.filter(
            company=company,
            realm_id=realm_id,
            flag_type__in=(
                FlagType.CONNECTWISE_UNBILLED,
                FlagType.CONNECTWISE_MARGIN,
                FlagType.CONNECTWISE_MISSING_MAPPING,
            ),
        ).delete()
        Flag.objects.bulk_create(flags_to_create)

    logger.info(
        "run_connectwise_reconciliation(%s, %s): clients=%s unbilled=%s margin=%s missing=%s",
        month,
        realm_id,
        clients_checked,
        unbilled_flags,
        margin_flags,
        missing_mappings,
    )

    return {
        "month": month,
        "realm_id": realm_id,
        "clients_checked": clients_checked,
        "unbilled_flags": unbilled_flags,
        "margin_flags": margin_flags,
        "missing_mappings": missing_mappings,
    }
