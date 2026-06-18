"""Views for the QuickBooks OAuth flow (Prompt 3) and the review dashboard (Prompt 13).

OAuth endpoints:
* ``qb_oauth_start`` — redirects the user to Intuit's authorize URL.
* ``qb_oauth_callback`` — receives the code, verifies state, stores tokens.

Dashboard endpoints:
* ``dashboard`` — month selector, open flags table, close summary section.
* ``qb_sync_now`` — pull the latest QuickBooks transactions.
* ``reconcile_month`` — run reconciliation + anomaly detection for a month.
* ``draft_summary`` — draft a close summary for a month.
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
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from core.agent.summary import draft_close_summary
from core.anomaly.rules import run_anomaly_detection
from core.models import CloseSummary, CloseSummaryStatus, Flag, FlagStatus, Transaction
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens
from core.reconciliation.engine import run_reconciliation


@require_http_methods(["GET"])
def home(request):
    """Landing page for anonymous users; redirect authenticated users to the dashboard."""
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse("core:dashboard"))
    return render(request, "core/home.html")


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
    return HttpResponseRedirect(reverse("core:dashboard"))


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


def _dashboard_context(month: str) -> dict:
    """Build the dashboard context for ``month``."""
    first, last = _month_bounds(month)

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

    has_data = Transaction.objects.filter(date__range=(first, last)).exists()

    return {
        "month": month,
        "months": months,
        "flags": flags,
        "flag_counts": flag_counts,
        "summary": summary,
        "has_data": has_data,
    }


def _render_dashboard(request, month: str, notice: str = ""):
    """Render the dashboard (full page or HTMX partial) for ``month``."""
    context = _dashboard_context(month)
    context["notice"] = notice
    template = (
        "core/dashboard_content.html"
        if getattr(request, "htmx", False)
        else "core/dashboard.html"
    )
    return render(request, template, context)


@login_required
@require_http_methods(["GET"])
def dashboard(request):
    """Render the monthly close review dashboard for a selected month."""
    month = request.GET.get("month")
    if not month:
        months = _available_months()
        month = months[0] if months else dt.date.today().strftime("%Y-%m")

    try:
        _month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    return _render_dashboard(request, month)


@login_required
@require_POST
def qb_sync_now(request):
    """Pull the latest QuickBooks transactions and refresh the dashboard."""
    month = request.POST.get("month") or dt.date.today().strftime("%Y-%m")

    token = qb_tokens.get_active_token()
    if token is None:
        return _render_dashboard(
            request,
            month,
            notice="QuickBooks is not connected. Please connect QuickBooks first.",
        )

    try:
        qb = qb_client.build_quickbooks_client(token)
        result = qb_client.sync_transactions(qb, qb_token=token)
    except Exception as exc:  # noqa: BLE001
        return _render_dashboard(
            request,
            month,
            notice=f"QuickBooks sync failed: {exc}",
        )

    if result.get("errors"):
        return _render_dashboard(
            request,
            month,
            notice=f"QuickBooks sync failed: {result.get('error_message', 'unknown error')}",
        )

    notice = (
        f"QuickBooks sync complete: created {result['created']}, "
        f"skipped {result['skipped']}."
    )
    return _render_dashboard(request, month, notice=notice)


@login_required
@require_POST
def reconcile_month(request):
    """Run reconciliation + anomaly detection for a month and refresh the dashboard."""
    month = request.POST.get("month") or dt.date.today().strftime("%Y-%m")

    try:
        _month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    rec = run_reconciliation(month)
    anomaly = run_anomaly_detection(month)

    rec_flags = rec.get("flags_created", 0)
    anomaly_flags = anomaly.get("anomaly_flags_created", 0)
    notice = f"Reconciliation complete: {rec_flags} reconciliation flag(s), {anomaly_flags} anomaly flag(s)."
    return _render_dashboard(request, month, notice=notice)


@login_required
@require_POST
def draft_summary(request):
    """Draft (or re-draft) a close summary for a month and refresh the dashboard."""
    month = request.POST.get("month") or dt.date.today().strftime("%Y-%m")

    try:
        _month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    try:
        summary = draft_close_summary(month)
    except Exception as exc:  # noqa: BLE001
        return _render_dashboard(
            request,
            month,
            notice=f"Close summary draft failed: {exc}",
        )

    notice = f"Close summary drafted for {summary.month}."
    return _render_dashboard(request, month, notice=notice)


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