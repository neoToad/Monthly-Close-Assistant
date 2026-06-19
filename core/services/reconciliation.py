"""Account-reconciliation orchestration service.

Pure-Python service layer for the account-level reconciliation apply flow. The view
and management command are thin wrappers that extract parameters and translate the
service result into HTTP or CLI output.
"""
from __future__ import annotations

import logging
from decimal import Decimal
from typing import Any, Optional

from core.agent import reconcile as reconcile_agent
from core.common.constants import BALANCE_TOLERANCE
from core.models import (
    AccountReconciliationState,
    BankStatementBalance,
    Flag,
    FlagStatus,
    FlagType,
    QuickBooksCompany,
    ReconciliationStatus,
)
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens
from core.quickbooks import writes as qb_writes
from core.reconciliation.engine import run_reconciliation

logger = logging.getLogger(__name__)


def _private_note(month: str, description: str) -> str:
    return f"AI-assisted reconciliation for {month} — {description}"


def apply_account_reconciliation_suggestions(
    month: str,
    realm_id: str,
    qb_account_id: str,
    suggestion_ids: list[str],
    dry_run: bool = True,
    user: Optional[Any] = None,
) -> dict[str, Any]:
    """Preview or apply selected reconciliation suggestions for a single account/month.

    In dry-run mode this returns a preview of the QB objects that would be created
    without writing anything. In apply mode it builds the QB client from the active
    token, writes each selected suggestion, re-syncs transactions, re-runs
    reconciliation, updates ``AccountReconciliationState``, and writes an audit note
    to the balance-reconciliation ``Flag``.

    The returned dict is intentionally flat so it can be consumed by both the HTTP
    view (which renders partials) and the management command (which prints messages
    or raises ``CommandError``).
    """
    suggestions_result = reconcile_agent.suggest_account_fixes(
        month, realm_id, qb_account_id
    )
    all_suggestions = suggestions_result["suggestions"]
    selected = [s for s in all_suggestions if s.get("id") in suggestion_ids]

    preview_objects = [
        {
            "object_type": s["type"].replace("_", " ").title(),
            "description": s.get("description", ""),
            "amount": s.get("amount", ""),
        }
        for s in selected
    ]

    result: dict[str, Any] = {
        "success": True,
        "month": month,
        "realm_id": realm_id,
        "qb_account_id": qb_account_id,
        "dry_run": dry_run,
        "account_name": suggestions_result["account_name"],
        "statement_balance": suggestions_result["statement_balance"] or Decimal("0"),
        "posted_total": suggestions_result["posted_total"],
        "difference": suggestions_result["difference"] or Decimal("0"),
        "suggestions": all_suggestions,
        "selected": selected,
        "preview_objects": preview_objects,
        "created_objects": [],
        "state_updated": False,
        "error": None,
        "notice": None,
        "token_missing": False,
        "client_error": None,
        "write_error": None,
        "sync_error": None,
    }

    if dry_run or not selected:
        result["notice"] = (
            f"Previewing {len(selected)} adjustment(s) for {result['account_name']}."
            if selected
            else f"No selected suggestions for {result['account_name']}."
        )
        return result

    token = qb_tokens.get_active_token(realm_id=realm_id)
    if token is None:
        result["success"] = False
        result["token_missing"] = True
        result["error"] = "QuickBooks is not connected. Please connect QuickBooks first."
        return result

    try:
        qb = qb_client.build_quickbooks_client(token)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Could not build QuickBooks client for %s: %s", realm_id, exc)
        result["success"] = False
        result["client_error"] = str(exc)
        result["error"] = f"Could not build QuickBooks client: {exc}"
        return result

    created_objects: list[dict[str, Any]] = []
    try:
        for suggestion in selected:
            created = qb_writes.apply_suggestion(
                qb,
                suggestion,
                realm_id=realm_id,
                private_note=_private_note(month, suggestion.get("description", "")),
            )
            created_objects.append(created)
    except Exception as exc:  # noqa: BLE001
        logger.exception("apply_suggestion failed for %s/%s", realm_id, qb_account_id)
        result["success"] = False
        result["write_error"] = str(exc)
        result["error"] = f"QuickBooks write failed: {exc}"
        result["created_objects"] = created_objects
        return result

    result["created_objects"] = created_objects

    try:
        qb_client.sync_transactions(qb, qb_token=token, realm_id=realm_id)
    except Exception as exc:  # noqa: BLE001
        logger.warning("Post-apply sync failed for %s/%s: %s", realm_id, qb_account_id, exc)
        result["sync_error"] = str(exc)

    run_reconciliation(month, realm_id=realm_id)

    company = QuickBooksCompany.objects.for_realm(realm_id)
    try:
        state = AccountReconciliationState.objects.get(
            company=company, qb_account_id=qb_account_id, month=month
        )
        applied = set(state.applied_suggestions or [])
        applied.update(suggestion_ids)
        state.applied_suggestions = list(applied)
        if state.difference and abs(state.difference) <= BALANCE_TOLERANCE:
            state.status = ReconciliationStatus.RECONCILED
        else:
            state.status = ReconciliationStatus.IN_PROGRESS
        state.save(update_fields=["applied_suggestions", "status"])
        result["state_updated"] = True
    except AccountReconciliationState.DoesNotExist:
        pass

    try:
        balance = BankStatementBalance.objects.get(
            company=company, qb_account_id=qb_account_id, month=month
        )
        flag = Flag.objects.filter(
            bank_statement_balance=balance,
            flag_type=FlagType.BALANCE_RECONCILIATION,
            status=FlagStatus.OPEN,
        ).first()
        if flag and created_objects:
            flag.notes = (
                f"Created {len(created_objects)} QuickBooks object(s): "
                + ", ".join(f"{obj['object_type']} {obj['id']}" for obj in created_objects)
                + "."
            )
            flag.save(update_fields=["notes"])
    except BankStatementBalance.DoesNotExist:
        pass

    result["notice"] = (
        f"Applied {len(created_objects)} adjustment(s) to QuickBooks for {result['account_name']}."
    )
    return result
