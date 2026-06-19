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

import datetime as dt
import logging

from decimal import Decimal
from typing import Any, Optional

from django.contrib.auth.decorators import login_required
from django.db.models import Q, Sum
from django.http import HttpResponse, HttpResponseBadRequest, HttpResponseRedirect
from django.shortcuts import get_object_or_404, render
from django.urls import reverse
from django.views.decorators.http import require_http_methods, require_POST

from core.agent import reconcile as reconcile_agent
from core.agent.summary import draft_close_summary
from core.anomaly.rules import run_anomaly_detection
from core.bank_feed import generate_bank_feed
from core.common.constants import BALANCE_TOLERANCE, CASH_LIKE_ACCOUNT_TYPES
from core.common.dates import month_bounds
from core.models import (
    BankStatementBalance,
    CloseSummary,
    CloseSummaryStatus,
    Flag,
    FlagStatus,
    QBAccount,
    QuickBooksCompany,
    Transaction,
)
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens
from core.reconciliation.engine import compute_posted_total, run_reconciliation
from core.services.reconciliation import apply_account_reconciliation_suggestions

logger = logging.getLogger(__name__)


@login_required
@require_http_methods(["GET"])
def reconcile_account_suggest(request, qb_account_id: str) -> HttpResponse:
    """Show the reconcile-account modal with AI-generated suggestions.

    Builds a QuickBooks client when an active token is available so the agent can
    optionally include live current-balance data. If the client cannot be built,
    the modal still renders with deterministic suggestions; a warning is logged.
    """
    month = request.GET.get("month") or dt.date.today().strftime("%Y-%m")
    realm_id = request.GET.get("realm_id") or _default_realm_id() or ""

    try:
        month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    qb_api_client: Any | None = None
    token = qb_tokens.get_active_token(realm_id=realm_id)
    if token is not None:
        try:
            qb_api_client = qb_client.build_quickbooks_client(token)
        except Exception as exc:  # noqa: BLE001
            logger.warning("Could not build QB client for suggestions: %s", exc)

    suggestions_result = reconcile_agent.suggest_account_fixes(
        month, realm_id, qb_account_id, qb_api_client=qb_api_client
    )
    inputs = reconcile_agent.gather_account_inputs(
        month, realm_id, qb_account_id, qb_api_client=qb_api_client
    )

    context = {
        "month": month,
        "realm_id": realm_id,
        "qb_account_id": qb_account_id,
        "account_name": suggestions_result["account_name"],
        "statement_balance": suggestions_result["statement_balance"] or Decimal("0"),
        "posted_total": suggestions_result["posted_total"],
        "difference": suggestions_result["difference"] or Decimal("0"),
        "qb_current_balance": Decimal(inputs.get("qb_current_balance") or 0),
        "suggestions": suggestions_result["suggestions"],
        "unmatched_bank": inputs["unmatched_bank"],
        "unmatched_gl": inputs["unmatched_gl"],
        "matched_differences": inputs["matched_differences"],
        "environment": qb_client.get_environment(),
        "preview": False,
    }
    return render(request, "core/reconcile_account_modal.html", context)


@login_required
@require_POST
def reconcile_account_apply(request, qb_account_id: str) -> HttpResponse:
    """Preview or apply selected reconciliation suggestions to QuickBooks.

    Delegates all business orchestration to
    ``core.services.reconciliation.apply_account_reconciliation_suggestions``. This
    view only validates HTTP parameters and renders the appropriate partial.
    """
    month = request.POST.get("month") or dt.date.today().strftime("%Y-%m")
    realm_id = request.POST.get("realm_id") or _default_realm_id() or ""
    suggestion_ids = request.POST.getlist("suggestion_ids")
    dry_run = request.POST.get("dry_run", "true").lower() not in ("false", "0", "")

    try:
        month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    result = apply_account_reconciliation_suggestions(
        month=month,
        realm_id=realm_id,
        qb_account_id=qb_account_id,
        suggestion_ids=suggestion_ids,
        dry_run=dry_run,
        user=request.user,
    )

    if result["dry_run"]:
        context = {
            "month": month,
            "realm_id": realm_id,
            "qb_account_id": qb_account_id,
            "account_name": result["account_name"],
            "statement_balance": result["statement_balance"],
            "posted_total": result["posted_total"],
            "difference": result["difference"],
            "suggestions": result["suggestions"],
            "preview": True,
            "preview_objects": result["preview_objects"],
            "environment": qb_client.get_environment(),
        }
        return render(request, "core/reconcile_account_modal.html", context)

    if not result["success"]:
        context = _bank_balances_context(month, realm_id=realm_id)
        context["month"] = month
        context["notice"] = result["error"] or "Reconciliation apply failed."
        return render(request, "core/bank_balances_section.html", context)

    context = _bank_balances_context(month, realm_id=realm_id)
    context["month"] = month
    context["notice"] = result["notice"] or (
        f"Applied {len(result['created_objects'])} adjustment(s) to QuickBooks for {result['account_name']}."
    )
    return render(request, "core/bank_balances_section.html", context)


@require_http_methods(["GET"])
def home(request) -> HttpResponse:
    """Landing page for anonymous users; redirect authenticated users to the dashboard."""
    if request.user.is_authenticated:
        return HttpResponseRedirect(reverse("core:dashboard"))
    return render(request, "core/home.html")


@require_http_methods(["GET"])
def qb_oauth_start(request) -> HttpResponse:
    """Begin the OAuth flow: redirect to Intuit's authorize URL."""
    try:
        url = qb_client.get_authorization_url(request.session)
    except ValueError:
        return HttpResponseBadRequest("QuickBooks OAuth is not configured.")
    return HttpResponseRedirect(url)


@require_http_methods(["GET"])
def qb_oauth_callback(request) -> HttpResponse:
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
        token = qb_tokens.store_tokens(exchanged, realm_id=realm_id)
    except Exception:  # noqa: BLE001 — surface any exchange/storage failure to the user
        return HttpResponseBadRequest("QuickBooks token exchange failed.")

    # Best-effort fetch of the company display name; never block the OAuth redirect.
    try:
        qb = qb_client.build_quickbooks_client(token)
        name = qb_client.fetch_company_name(qb, qb_token=token)
        if name:
            QuickBooksCompany.objects.filter(realm_id=realm_id).update(name=name)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not fetch company name for realm %s: %s", realm_id, exc)

    request.session.pop("qb_oauth_state", None)
    return HttpResponseRedirect(reverse("core:dashboard"))


# ---------------------------------------------------------------------------
# Review dashboard (Prompt 13)
# ---------------------------------------------------------------------------


def _available_months(realm_id: Optional[str] = None) -> list[str]:
    """Distinct months that have at least one transaction, newest first."""
    qs = Transaction.objects.all()
    if realm_id:
        qs = qs.filter(realm_id=realm_id)
    dates = qs.dates("date", "month", order="DESC")
    return [f"{d.year}-{d.month:02d}" for d in dates]


def _bank_balances_context(month: str, realm_id: Optional[str] = None) -> dict[str, Any]:
    """Build the bank balances panel context for ``month`` and optional ``realm_id``.

    Returns a dict with:
    - ``balances``: a list of account snapshots (name, bank_balance, posted_total,
      difference, is_reconciled).
    - ``cash_accounts``: cash-like QBAccount rows for the realm/month, used to
      populate the "set balance" form.
    """
    balances_qs = BankStatementBalance.objects.filter(month=month)
    if realm_id:
        balances_qs = balances_qs.filter(realm_id=realm_id)

    snapshots: list[dict[str, Any]] = []
    for balance in balances_qs:
        posted_total = compute_posted_total(
            month,
            balance.account_name,
            realm_id=balance.realm_id,
        )
        difference = balance.ending_balance - posted_total
        snapshots.append(
            {
                "account_name": balance.account_name,
                "qb_account_id": balance.qb_account_id,
                "bank_balance": balance.ending_balance,
                "posted_total": posted_total,
                "difference": difference,
                "is_reconciled": abs(difference) <= BALANCE_TOLERANCE,
                "source": balance.source,
            }
        )

    cash_accounts = QBAccount.objects.filter(
        account_type__in=CASH_LIKE_ACCOUNT_TYPES,
        active=True,
    )
    if realm_id:
        cash_accounts = cash_accounts.filter(realm_id=realm_id)

    return {
        "balances": snapshots,
        "cash_accounts": cash_accounts,
        "has_bank_balances": bool(snapshots) or cash_accounts.exists() or bool(realm_id),
    }


def _dashboard_context(month: str, realm_id: Optional[str] = None) -> dict[str, Any]:
    """Build the dashboard context for ``month`` and optional ``realm_id``."""
    first, last = month_bounds(month)

    flag_filters = Q(transaction__date__range=(first, last)) | Q(
        bank_transaction__date__range=(first, last)
    )
    if realm_id:
        flag_filters &= Q(realm_id=realm_id)

    month_flags = Flag.objects.filter(flag_filters)

    flags = month_flags.filter(status=FlagStatus.OPEN).select_related(
        "transaction", "bank_transaction"
    ).order_by("-created_at")

    flag_counts = {
        "open": month_flags.filter(status=FlagStatus.OPEN).count(),
        "approved": month_flags.filter(status=FlagStatus.APPROVED).count(),
        "rejected": month_flags.filter(status=FlagStatus.REJECTED).count(),
    }

    summary_qs = CloseSummary.objects.filter(month=month)
    if realm_id:
        summary_qs = summary_qs.filter(realm_id=realm_id)
    summary = summary_qs.first()

    months = _available_months(realm_id=realm_id)

    txn_qs = Transaction.objects.filter(date__range=(first, last))
    if realm_id:
        txn_qs = txn_qs.filter(realm_id=realm_id)
    has_data = txn_qs.exists()

    context = {
        "month": month,
        "months": months,
        "realm_id": realm_id,
        "flags": flags,
        "flag_counts": flag_counts,
        "summary": summary,
        "has_data": has_data,
    }
    context.update(_bank_balances_context(month, realm_id=realm_id))
    return context


def _default_realm_id() -> Optional[str]:
    """Return the most recently connected realm id, or None when no token exists."""
    token = qb_tokens.get_active_token()
    return token.realm_id if token else None


def _request_realm_id(request) -> Optional[str]:
    """Return the realm id from the request, falling back to the active token."""
    realm_id = request.POST.get("realm_id") or request.GET.get("company")
    if realm_id:
        return realm_id
    return _default_realm_id()


def _render_dashboard(
    request, month: str, realm_id: Optional[str] = None, notice: str = ""
) -> HttpResponse:
    """Render the dashboard (full page or HTMX partial) for ``month`` and ``realm_id``."""
    context = _dashboard_context(month, realm_id=realm_id)
    context["notice"] = notice
    context["companies"] = QuickBooksCompany.objects.filter(is_connected=True)
    template = (
        "core/dashboard_content.html"
        if getattr(request, "htmx", False)
        else "core/dashboard.html"
    )
    return render(request, template, context)


@login_required
@require_http_methods(["GET"])
def dashboard(request) -> HttpResponse:
    """Render the monthly close review dashboard for a selected company and month."""
    realm_id = request.GET.get("company") or _default_realm_id()
    month = request.GET.get("month")
    if not month:
        months = _available_months(realm_id=realm_id)
        month = months[0] if months else dt.date.today().strftime("%Y-%m")

    try:
        month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    return _render_dashboard(request, month, realm_id=realm_id)


@login_required
@require_POST
def qb_sync_now(request) -> HttpResponse:
    """Pull the latest QuickBooks transactions and refresh the dashboard."""
    month = request.POST.get("month") or dt.date.today().strftime("%Y-%m")
    realm_id = _request_realm_id(request)

    token = qb_tokens.get_active_token(realm_id=realm_id)
    if token is None:
        return _render_dashboard(
            request,
            month,
            notice="QuickBooks is not connected. Please connect QuickBooks first.",
        )

    try:
        qb = qb_client.build_quickbooks_client(token)
        result = qb_client.sync_transactions(qb, qb_token=token, realm_id=token.realm_id)
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
def reconcile_month(request) -> HttpResponse:
    """Run reconciliation + anomaly detection for a month and refresh the dashboard."""
    month = request.POST.get("month") or dt.date.today().strftime("%Y-%m")
    realm_id = _request_realm_id(request)

    try:
        month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    rec = run_reconciliation(month, realm_id=realm_id or "")
    anomaly = run_anomaly_detection(month, realm_id=realm_id or "")

    rec_flags = rec.get("flags_created", 0)
    anomaly_flags = anomaly.get("anomaly_flags_created", 0)
    notice = f"Reconciliation complete: {rec_flags} reconciliation flag(s), {anomaly_flags} anomaly flag(s)."
    return _render_dashboard(request, month, realm_id=realm_id, notice=notice)


@login_required
@require_POST
def draft_summary(request) -> HttpResponse:
    """Draft (or re-draft) a close summary for a month and refresh the dashboard."""
    month = request.POST.get("month") or dt.date.today().strftime("%Y-%m")
    realm_id = _request_realm_id(request)

    try:
        month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    try:
        summary = draft_close_summary(month, realm_id=realm_id or "")
    except Exception as exc:  # noqa: BLE001
        return _render_dashboard(
            request,
            month,
            realm_id=realm_id,
            notice=f"Close summary draft failed: {exc}",
        )

    notice = f"Close summary drafted for {summary.month}."
    return _render_dashboard(request, month, realm_id=realm_id, notice=notice)


@login_required
@require_POST
def flag_approve(request, flag_id: int) -> HttpResponse:
    """Approve a flag and return its updated table row partial."""
    flag = get_object_or_404(Flag, id=flag_id)
    flag.status = FlagStatus.APPROVED
    flag.save(update_fields=["status"])
    return render(request, "core/flag_row.html", {"flag": flag})


@login_required
@require_POST
def flag_reject(request, flag_id: int) -> HttpResponse:
    """Reject a flag and return its updated table row partial."""
    flag = get_object_or_404(Flag, id=flag_id)
    flag.status = FlagStatus.REJECTED
    flag.save(update_fields=["status"])
    return render(request, "core/flag_row.html", {"flag": flag})


@login_required
@require_POST
def set_bank_balance(request) -> HttpResponse:
    """Create or update a ``BankStatementBalance`` row from the dashboard.

    Expects ``month``, ``realm_id``, ``qb_account_id``, and ``ending_balance`` in POST
    data. Returns the bank balances section partial so HTMX can swap it in place.
    """
    month = request.POST.get("month")
    realm_id = request.POST.get("realm_id")
    account_id = request.POST.get("qb_account_id")
    balance_str = request.POST.get("ending_balance", "").strip()

    if not month or not account_id or not balance_str:
        return HttpResponseBadRequest("Month, account, and balance are required.")

    try:
        month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    try:
        ending_balance = Decimal(balance_str)
    except Exception:
        return HttpResponseBadRequest("Balance must be a valid decimal number.")

    company = QuickBooksCompany.objects.for_realm(realm_id or "")
    account = get_object_or_404(
        QBAccount,
        company=company,
        realm_id=realm_id or "",
        account_id=account_id,
    )

    BankStatementBalance.objects.update_or_create(
        company=company,
        qb_account_id=account_id,
        month=month,
        defaults={
            "realm_id": realm_id or "",
            "account_name": account.name,
            "ending_balance": ending_balance,
            "source": BankStatementBalance.Source.MANUAL,
        },
    )

    context = _bank_balances_context(month, realm_id=realm_id)
    context["month"] = month
    return render(request, "core/bank_balances_section.html", context)


@login_required
@require_POST
def generate_bank_feed_view(request) -> HttpResponse:
    """Generate synthetic BankTransaction records for the month and refresh dashboard."""
    month = request.POST.get("month") or dt.date.today().strftime("%Y-%m")
    realm_id = _request_realm_id(request)

    try:
        month_bounds(month)
    except (ValueError, IndexError):
        return HttpResponseBadRequest("Invalid month. Use YYYY-MM.")

    force = request.POST.get("force") == "true"
    cash_only = request.POST.get("cash_only") == "true"

    try:
        result = generate_bank_feed(
            month=month,
            realm_id=realm_id or "",
            force=force,
            cash_only=cash_only,
        )
    except ValueError as exc:
        return _render_dashboard(
            request,
            month,
            realm_id=realm_id,
            notice=str(exc),
        )
    except Exception as exc:  # noqa: BLE001
        logger.exception("Bank feed generation failed for %s/%s", realm_id, month)
        return _render_dashboard(
            request,
            month,
            realm_id=realm_id,
            notice=f"Bank feed generation failed: {exc}",
        )

    if result.get("message"):
        notice = result["message"]
    else:
        notice = (
            f"Bank feed generated for {month}: {result['created']} bank row(s) "
            f"({result['dropped']} dropped, {result['duplicated']} duplicated, "
            f"{result['amount_shifts']} amount shifts, {result['date_shifts']} date shifts, "
            f"{result['extras']} extras)."
        )
    return _render_dashboard(request, month, realm_id=realm_id, notice=notice)


@login_required
@require_POST
def summary_review(request, month: str) -> HttpResponse:
    """Mark a company's close summary for ``month`` as reviewed with optional notes."""
    realm_id = request.POST.get("realm_id")
    filters = {"month": month}
    if realm_id:
        filters["realm_id"] = realm_id
    summary = get_object_or_404(CloseSummary, **filters)
    summary.status = CloseSummaryStatus.REVIEWED
    summary.reviewer_notes = request.POST.get("reviewer_notes", "")
    summary.save(update_fields=["status", "reviewer_notes"])
    return render(request, "core/close_summary_section.html", {"summary": summary})
