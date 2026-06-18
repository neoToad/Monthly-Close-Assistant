"""Views for the QuickBooks OAuth flow (Prompt 3) and the review dashboard (Prompt 13).

OAuth endpoints:
* ``qb_oauth_start`` — redirects the user to Intuit's authorize URL.
* ``qb_oauth_callback`` — receives the code, verifies state, stores tokens.

Dashboard endpoints:
* ``dashboard`` — month selector, open flags table, close summary section.
* ``flag_approve`` / ``flag_reject`` — update a flag status (HTMX row swap).
* ``summary_review`` — mark a close summary reviewed with notes.
"""
from __future__ import annotations

import calendar
import datetime as dt

from django.contrib.auth.decorators import login_required
from django.db.models import Q
from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.views.decorators.http import require_http_methods, require_POST

from core.models import CloseSummary, CloseSummaryStatus, Flag, FlagStatus, Transaction
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens


@require_http_methods(["GET"])
def qb_oauth_start(request):
    """Begin the OAuth flow: redirect to Intuit's authorize URL."""
    try:
        url = qb_client.get_authorization_url(request.session)
    except ValueError:
        return HttpResponseBadRequest("QuickBooks OAuth is not configured.")
    return HttpResponseRedirect(url)


@require_http_methods(["GET"])
def qb_oauth_callback(request):
    """Complete the OAuth flow: verify state, exchange the code, store tokens."""
    code = request.GET.get("code")
    realm_id = request.GET.get("realmId")
    state = request.GET.get("state")

    if not code or not realm_id:
        return HttpResponseBadRequest("Missing code or realmId.")

    expected_state = request.session.get("qb_oauth_state")
    if not state or not expected_state or state != expected_state:
        return HttpResponseBadRequest("Invalid OAuth state.")

    try:
        auth_client = qb_client.make_auth_client(realm_id=realm_id)
        exchanged = qb_client.exchange_code_for_tokens(auth_client, code, realm_id)
        qb_tokens.store_tokens(exchanged, realm_id=realm_id)
    except Exception:  # noqa: BLE001 — surface any exchange/storage failure to the user
        return HttpResponseBadRequest("QuickBooks token exchange failed.")

    request.session.pop("qb_oauth_state", None)
    return HttpResponseRedirect("/admin/")


# ---------------------------------------------------------------------------
# Review dashboard (Prompt 13)
# ---------------------------------------------------------------------------


def _month_bounds(month: str) -> tuple[dt.date, dt.date]:
    """Return (first_day, last_day) for a ``YYYY-MM`` string."""
    year, mon = int(month[:4]), int(month[5:7])
    first = dt.date(year, mon, 1)
    last = dt.date(year, mon, calendar.monthrange(year, mon)[1])
    return first, last


def _available_months() -> list[str]:
    """Distinct months that have at least one transaction, newest first."""
    dates = Transaction.objects.dates("date", "month", order="DESC")
    return [f"{d.year}-{d.month:02d}" for d in dates]


@login_required
@require_http_methods(["GET"])
def dashboard(request):
    """Render the monthly close review dashboard for a selected month."""
    month = request.GET.get("month")
    if not month:
        months = _available_months()
        month = months[0] if months else dt.date.today().strftime("%Y-%m")

    try:
        first, last = _month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    month_flags = Flag.objects.filter(
        Q(transaction__date__range=(first, last))
        | Q(bank_transaction__date__range=(first, last))
    )

    flags = month_flags.filter(status=FlagStatus.OPEN).select_related(
        "transaction", "bank_transaction"
    ).order_by("-created_at")

    flag_counts = {
        "open": month_flags.filter(status=FlagStatus.OPEN).count(),
        "approved": month_flags.filter(status=FlagStatus.APPROVED).count(),
        "rejected": month_flags.filter(status=FlagStatus.REJECTED).count(),
    }

    summary = CloseSummary.objects.filter(month=month).first()
    months = _available_months()

    context = {
        "month": month,
        "months": months,
        "flags": flags,
        "flag_counts": flag_counts,
        "summary": summary,
    }
    template = (
        "core/dashboard_content.html"
        if getattr(request, "htmx", False)
        else "core/dashboard.html"
    )
    return render(request, template, context)


@login_required
@require_POST
def flag_approve(request, flag_id: int):
    """Approve a flag and return its updated table row partial."""
    flag = get_object_or_404(Flag, id=flag_id)
    flag.status = FlagStatus.APPROVED
    flag.save(update_fields=["status"])
    return render(request, "core/flag_row.html", {"flag": flag})


@login_required
@require_POST
def flag_reject(request, flag_id: int):
    """Reject a flag and return its updated table row partial."""
    flag = get_object_or_404(Flag, id=flag_id)
    flag.status = FlagStatus.REJECTED
    flag.save(update_fields=["status"])
    return render(request, "core/flag_row.html", {"flag": flag})


@login_required
@require_POST
def summary_review(request, month: str):
    """Mark a month's close summary as reviewed with optional notes."""
    summary = get_object_or_404(CloseSummary, month=month)
    summary.status = CloseSummaryStatus.REVIEWED
    summary.reviewer_notes = request.POST.get("reviewer_notes", "")
    summary.save(update_fields=["status", "reviewer_notes"])
    return render(request, "core/close_summary_section.html", {"summary": summary})