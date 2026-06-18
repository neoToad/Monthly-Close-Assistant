"""QuickBooks Online OAuth, token refresh, data pull, and sync (Prompt 3).

This module is the single DRY boundary between the app and the QuickBooks /
intuit-oauth libraries. Everything network-facing (``AuthClient``, ``QuickBooks``,
and the raw record queries) lives behind small functions so the sync pipeline can
be tested against mocked responses.

Environment (all read via ``decouple.config`` from ``.env``):

* ``QB_CLIENT_ID`` / ``QB_CLIENT_SECRET`` — the Intuit app credentials.
* ``QB_REDIRECT_URI`` — the OAuth callback URL registered with Intuit.
* ``QB_SANDBOX_COMPANY_ID`` — the sandbox realm id used as the default company.

The Intuit ``environment`` is hardcoded to ``"sandbox"`` for now; ``QB_ENVIRONMENT``
is formalized in Prompt 4. Retry/backoff is deferred to Prompt 5.
"""
from __future__ import annotations

import datetime as dt
import logging
import secrets
from decimal import Decimal, InvalidOperation
from typing import Any, Optional

from decouple import config
from django.conf import settings
from django.utils import timezone
from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
from quickbooks.objects.deposit import Deposit
from quickbooks.objects.journalentry import JournalEntry
from quickbooks.objects.purchase import Purchase

from core.models import Transaction

logger = logging.getLogger(__name__)

#: Intuit environment to target. Hardcoded to sandbox for the Foundation stage;
#: Prompt 4 will make this configurable via ``QB_ENVIRONMENT``.
QB_ENVIRONMENT = "sandbox"

#: API base URL templates for each QuickBooks environment (Prompt 4).
API_BASE_URLS = {
    "sandbox": "https://sandbox-quickbooks.api.intuit.com/v3/company/",
    "production": "https://quickbooks.api.intuit.com/v3/company/",
}

#: The QuickBooks record types pulled during sync, mapped to their source_type.
SYNC_OBJECTS = {
    "Purchase": Purchase,
    "Deposit": Deposit,
    "JournalEntry": JournalEntry,
}


# ---------------------------------------------------------------------------
# Environment + API base URL (Prompt 4)
# ---------------------------------------------------------------------------


def get_environment() -> str:
    """Return the configured QuickBooks environment (``sandbox`` or ``production``).

    Reads ``QB_ENVIRONMENT`` from Django settings (sourced from the environment via
    python-decouple). Defaults to ``sandbox`` when unset or blank. Raises
    ``ValueError`` for any other value.
    """
    env = (getattr(settings, "QB_ENVIRONMENT", "") or "sandbox").strip().lower()
    if env not in ("sandbox", "production"):
        raise ValueError(f"QB_ENVIRONMENT must be 'sandbox' or 'production', got {env!r}")
    return env


def get_api_base_url(environment: Optional[str] = None) -> str:
    """Return the QuickBooks v3 API base URL for ``environment``.

    Defaults to the currently configured environment. The returned URL ends with
    ``company/`` so callers can append a realm id.
    """
    env = environment or get_environment()
    if env not in API_BASE_URLS:
        raise ValueError(f"Unknown QuickBooks environment: {env!r}")
    return API_BASE_URLS[env]


# ---------------------------------------------------------------------------
# OAuth
# ---------------------------------------------------------------------------


def make_auth_client(realm_id: Optional[str] = None) -> AuthClient:
    """Build an Intuit ``AuthClient`` from the env-configured app credentials."""
    client_id = config("QB_CLIENT_ID", default="")
    client_secret = config("QB_CLIENT_SECRET", default="")
    redirect_uri = config("QB_REDIRECT_URI", default="")
    if not (client_id and client_secret and redirect_uri):
        raise ValueError(
            "QuickBooks OAuth is not configured: set QB_CLIENT_ID, QB_CLIENT_SECRET, "
            "and QB_REDIRECT_URI in the environment."
        )
    return AuthClient(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=redirect_uri,
        environment=get_environment(),
        realm_id=realm_id,
    )


def get_authorization_url(session) -> str:
    """Return the Intuit authorize URL, stashing a CSRF state in ``session``."""
    auth_client = make_auth_client()
    state = secrets.token_urlsafe(24)
    session["qb_oauth_state"] = state
    return auth_client.get_authorization_url(scopes=[Scopes.ACCOUNTING], state_token=state)


def exchange_code_for_tokens(auth_client: AuthClient, code: str, realm_id: str) -> AuthClient:
    """Exchange an authorization code for access/refresh tokens (mutates ``auth_client``)."""
    auth_client.realm_id = realm_id
    auth_client.get_bearer_token(auth_code=code, realm_id=realm_id)
    return auth_client


def refresh_tokens(auth_client: AuthClient) -> dict:
    """Refresh the access token and return the new tokens + expiry datetimes."""
    auth_client.refresh()
    now = timezone.now()
    expires_in = getattr(auth_client, "expires_in", None)
    x_refresh_expires_in = getattr(auth_client, "x_refresh_token_expires_in", None)
    return {
        "access_token": getattr(auth_client, "access_token", None),
        "refresh_token": getattr(auth_client, "refresh_token", None),
        "access_token_expires_at": (
            now + dt.timedelta(seconds=int(expires_in)) if expires_in else None
        ),
        "refresh_token_expires_at": (
            now + dt.timedelta(seconds=int(x_refresh_expires_in))
            if x_refresh_expires_in
            else None
        ),
    }


# ---------------------------------------------------------------------------
# Data pull + normalization
# ---------------------------------------------------------------------------


def build_quickbooks_client(qb_token) -> QuickBooks:
    """Build a ``QuickBooks`` API client from a stored ``QBToken``."""
    environment = get_environment()
    auth_client = AuthClient(
        client_id=config("QB_CLIENT_ID", default=""),
        client_secret=config("QB_CLIENT_SECRET", default=""),
        redirect_uri=config("QB_REDIRECT_URI", default=""),
        environment=environment,
        access_token=qb_token.get_access_token(),
        refresh_token=qb_token.get_refresh_token(),
        realm_id=qb_token.realm_id,
    )
    return QuickBooks(
        auth_client=auth_client,
        company_id=qb_token.realm_id,
        refresh_token=qb_token.get_refresh_token(),
        minorversion=75,
    )


def pull_raw_records(qb_client: QuickBooks) -> dict:
    """Pull all Purchase / Deposit / JournalEntry records as a dict of lists."""
    return {
        source_type: model.all(qb=qb_client)
        for source_type, model in SYNC_OBJECTS.items()
    }


def _ref_name(ref: Any) -> str:
    """Best-effort name from a python-quickbooks ``Ref`` (``.name`` then ``.value``)."""
    if ref is None:
        return ""
    return getattr(ref, "name", "") or getattr(ref, "value", "") or ""


def _parse_date(value: Any) -> Optional[dt.date]:
    if not value:
        return None
    try:
        return dt.datetime.strptime(str(value), "%Y-%m-%d").date()
    except (ValueError, TypeError):
        return None


def _to_decimal(value: Any) -> Decimal:
    try:
        return Decimal(str(value))
    except (InvalidOperation, TypeError, ValueError):
        return Decimal("0")


def _first_debit_account(record: Any) -> str:
    """The GL account from the first debit line of a JournalEntry (fallback: any line)."""
    lines = getattr(record, "Line", None) or []
    for line in lines:
        if getattr(line, "PostingType", "") == "Debit":
            detail = getattr(line, "JournalEntryLineDetail", None)
            return _ref_name(getattr(detail, "AccountRef", None)) if detail else ""
    for line in lines:
        detail = getattr(line, "JournalEntryLineDetail", None)
        if detail is not None:
            return _ref_name(getattr(detail, "AccountRef", None))
    return ""


def normalize_record(record: Any, source_type: str) -> Optional[dict]:
    """Normalize a QuickBooks record into the ``Transaction`` field dict.

    Returns ``None`` when the record lacks an id or a parseable date (so the caller
    can count it as skipped rather than creating a malformed Transaction).
    """
    qb_id = str(getattr(record, "Id", "") or "")
    txn_date = _parse_date(getattr(record, "TxnDate", ""))
    if not qb_id or txn_date is None:
        return None

    amount = _to_decimal(getattr(record, "TotalAmt", 0))

    if source_type == "Purchase":
        vendor = _ref_name(getattr(record, "EntityRef", None)) or "Unknown Vendor"
        gl_account = _ref_name(getattr(record, "AccountRef", None))
    elif source_type == "Deposit":
        vendor = "Deposit"
        gl_account = _ref_name(getattr(record, "DepositToAccountRef", None))
    elif source_type == "JournalEntry":
        vendor = "Journal Entry"
        gl_account = _first_debit_account(record)
    else:
        vendor = getattr(record, "qbo_object_name", "") or "Unknown"
        gl_account = ""

    return {
        "qb_transaction_id": qb_id,
        "date": txn_date,
        "vendor": vendor,
        "amount": amount,
        "category": "",
        "gl_account": gl_account,
        "source_type": source_type,
    }


def sync_transactions(qb_client: QuickBooks) -> dict:
    """Pull QuickBooks records and upsert them into ``Transaction`` (idempotent).

    Idempotency is keyed on ``qb_transaction_id``: existing rows are skipped (not
    overwritten). Returns a counts summary.
    """
    raw = pull_raw_records(qb_client)
    created = skipped = 0
    per_type: dict = {}

    for source_type, records in raw.items():
        per_type[source_type] = {"created": 0, "skipped": 0}
        for record in records:
            normalized = normalize_record(record, source_type)
            if normalized is None:
                skipped += 1
                per_type[source_type]["skipped"] += 1
                continue
            defaults = {k: v for k, v in normalized.items() if k != "qb_transaction_id"}
            _obj, was_created = Transaction.objects.get_or_create(
                qb_transaction_id=normalized["qb_transaction_id"], defaults=defaults
            )
            if was_created:
                created += 1
                per_type[source_type]["created"] += 1
            else:
                skipped += 1
                per_type[source_type]["skipped"] += 1

    logger.info("sync_quickbooks: created=%s skipped=%s", created, skipped)
    return {"created": created, "skipped": skipped, "errors": 0, "per_type": per_type}