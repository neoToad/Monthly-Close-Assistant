"""Close-summary orchestration service.

Thin wrapper around the read-only close-summary agent. The caller (dashboard view or
management command) decides whether to build a QuickBooks client; this service fetches
the optional GeneralLedger cross-check totals and passes them to the agent as plain
inputs.
"""
from __future__ import annotations

import logging
from typing import Any, Optional

from core.agents.close_summary import draft_close_summary
from core.models import CloseSummary
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens

logger = logging.getLogger(__name__)


def orchestrate_close_summary(
    month: str,
    realm_id: Optional[str] = None,
    fetch_qb_gl_totals: bool = False,
) -> CloseSummary:
    """Draft a close summary for ``month`` and optional ``realm_id``.

    When ``fetch_qb_gl_totals`` is True and an active token exists, fetch the
    QuickBooks GeneralLedger summary and pass it to the agent. Failures are logged
    and the agent falls back to a deterministic summary without the cross-check.
    """
    qb_gl_totals: dict[str, Any] = {}
    if fetch_qb_gl_totals:
        token = qb_tokens.get_active_token(realm_id=realm_id or "")
        if token is not None:
            try:
                qb_api_client = qb_client.build_quickbooks_client(token)
                qb_gl_totals = qb_client.fetch_general_ledger_summary(
                    qb_api_client, month
                )
            except Exception as exc:  # noqa: BLE001 — GL cross-check is best-effort
                logger.warning(
                    "Failed to fetch QB GeneralLedger summary for %s/%s: %s",
                    realm_id,
                    month,
                    exc,
                )

    return draft_close_summary(month, realm_id=realm_id, qb_gl_totals=qb_gl_totals)
