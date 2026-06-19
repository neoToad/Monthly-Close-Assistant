"""QuickBooks Online OAuth, token refresh, data pull, and sync (Prompt 3).

This module is the single DRY boundary between the app and the QuickBooks /
intuit-oauth libraries. Everything network-facing (``AuthClient``, ``QuickBooks``,
and the raw record queries) lives behind small functions so the sync pipeline can
be tested against mocked responses.

Environment (all read via ``decouple.config`` from ``.env``):

* ``QB_CLIENT_ID`` / ``QB_CLIENT_SECRET`` — the Intuit app credentials.
* ``QB_REDIRECT_URI`` — the OAuth callback URL registered with Intuit.

The Intuit ``environment`` is hardcoded to ``"sandbox"`` for now; ``QB_ENVIRONMENT``
is formalized in Prompt 4. Retry/backoff is deferred to Prompt 5.
"""
from __future__ import annotations

import datetime as dt
import logging
import secrets
import time
from decimal import Decimal, InvalidOperation
from typing import Any, Callable, Optional

from decouple import config
from django.conf import settings
from intuitlib.client import AuthClient
from intuitlib.enums import Scopes
from quickbooks import QuickBooks
from quickbooks.exceptions import AuthorizationException, QuickbooksException
from quickbooks.objects.account import Account
from quickbooks.objects.bill import Bill
from quickbooks.objects.billpayment import BillPayment
from quickbooks.objects.company_info import CompanyInfo
from quickbooks.objects.deposit import Deposit
from quickbooks.objects.journalentry import JournalEntry
from quickbooks.objects.purchase import Purchase
from quickbooks.objects.vendorcredit import VendorCredit

from core.models import QBAccount, QuickBooksCompany, Transaction

logger = logging.getLogger(__name__)

#: Intuit environment to target. Hardcoded to sandbox for the Foundation stage;
#: Prompt 4 will make this configurable via ``QB_ENVIRONMENT``.
QB_ENVIRONMENT = "sandbox"

#: API base URL templates for each QuickBooks environment (Prompt 4).
API_BASE_URLS = {
    "sandbox": "https://sandbox-quickbooks.api.intuit.com/v3/company/",
    "production": "https://quickbooks.api.intuit.com/v3/company/",
}

SYNC_OBJECTS = {
    "Purchase": Purchase,
    "Deposit": Deposit,
    "JournalEntry": JournalEntry,
    "Bill": Bill,
    "BillPayment": BillPayment,
    "VendorCredit": VendorCredit,
}


#: Exceptions treated as transient network/API failures worthy of exponential backoff.
RETRYABLE_EXCEPTIONS = (
    QuickbooksException,
    ConnectionError,
    TimeoutError,
)


# ---------------------------------------------------------------------------
# Token refresh + retry wrapper (Prompt 5)
# ---------------------------------------------------------------------------


def refresh_and_store_tokens(qb_token) -> Any:
    """Refresh the access token for ``qb_token`` and persist the result.

    Builds a fresh ``AuthClient``, seeds it with the stored refresh token, calls
    ``AuthClient.refresh()``, and writes the new tokens back to ``QBToken`` via
    ``store_tokens``. Returns the refreshed ``QBToken`` row.
    """
    from core.quickbooks.tokens import store_tokens

    auth_client = make_auth_client(realm_id=qb_token.realm_id)
    auth_client.access_token = qb_token.get_access_token()
    auth_client.refresh_token = qb_token.get_refresh_token()
    auth_client.refresh()
    return store_tokens(auth_client, realm_id=qb_token.realm_id)


def call_with_retry(
    qb_client: QuickBooks,
    qb_token: Optional[Any],
    func: Callable,
    *args,
    **kwargs,
) -> Any:
    """Execute ``func(qb_client, *args, **kwargs)`` with auth refresh and retry logic.

    * If ``qb_token`` is expired or inside the refresh buffer, refresh proactively
      before the first attempt.
    * On ``AuthorizationException`` (mid-sync token expiry), refresh once and retry.
    * On transient errors (QuickbooksException, ConnectionError, TimeoutError), retry
      up to 3 more times with exponential backoff (2, 4, 8 seconds).
    * All retry/failure paths are logged clearly; the final exception is re-raised.
    """
    if qb_token is not None and qb_token.is_access_token_expired():
        logger.info(
            "QuickBooks access token expired or within refresh buffer; refreshing before sync."
        )
        qb_token = refresh_and_store_tokens(qb_token)
        qb_client = build_quickbooks_client(qb_token)

    try:
        return func(qb_client, *args, **kwargs)
    except AuthorizationException as exc:
        logger.warning(
            "QuickBooks authorization error mid-sync: %s. Refreshing token and retrying once.",
            exc,
        )
        if qb_token is None:
            logger.error("No stored token to refresh; failing loudly.")
            raise
        qb_token = refresh_and_store_tokens(qb_token)
        qb_client = build_quickbooks_client(qb_token)
        return func(qb_client, *args, **kwargs)
    except RETRYABLE_EXCEPTIONS as exc:
        max_attempts = 3
        for attempt in range(1, max_attempts + 1):
            sleep_seconds = 2 ** attempt
            logger.warning(
                "QuickBooks API transient error (attempt %s/%s): %s. Retrying in %ss.",
                attempt,
                max_attempts,
                exc,
                sleep_seconds,
            )
            time.sleep(sleep_seconds)
            try:
                return func(qb_client, *args, **kwargs)
            except RETRYABLE_EXCEPTIONS as retry_exc:
                exc = retry_exc
                if attempt == max_attempts:
                    logger.error(
                        "QuickBooks API still failing after %s attempts: %s",
                        max_attempts,
                        exc,
                    )
                    raise
        raise  # pragma: no cover


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


def fetch_company_name(qb_client: QuickBooks, qb_token: Optional[Any] = None) -> str:
    """Fetch the display name for the connected QuickBooks company.

    Reads the ``CompanyInfo`` endpoint (``GET /company/{realmId}/companyinfo/1``),
    returning ``CompanyName`` with a fallback to ``LegalName``. Logs a warning and
    returns ``""`` on failure so callers (OAuth callback, sync) never crash the
    user-facing flow.
    """

    def _fetch(client: QuickBooks) -> Any:
        return CompanyInfo.get(id=1, qb=client)

    try:
        info = call_with_retry(qb_client, qb_token, _fetch)
    except Exception as exc:  # noqa: BLE001 — name lookup is best-effort
        logger.warning("Failed to fetch QuickBooks company name: %s", exc)
        return ""

    return str(getattr(info, "CompanyName", "") or getattr(info, "LegalName", "") or "")



def pull_raw_records(qb_client: QuickBooks, qb_token: Optional[Any] = None) -> dict:
    """Pull all Purchase / Deposit / JournalEntry records as a dict of lists.

    Wraps each object query with ``call_with_retry`` so mid-sync auth expiry and
    transient API errors are handled automatically (Prompt 5).
    """
    def _fetch(client, model):
        return model.all(qb=client)

    return {
        source_type: call_with_retry(qb_client, qb_token, _fetch, model)
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


def _first_line_account(record: Any) -> str:
    """The GL account from the first Line.AccountRef of Bill / VendorCredit."""
    lines = getattr(record, "Line", None) or []
    for line in lines:
        account_ref = getattr(line, "AccountRef", None)
        if account_ref is not None:
            return _ref_name(account_ref)
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
    elif source_type == "Bill":
        vendor = _ref_name(getattr(record, "VendorRef", None)) or "Unknown Vendor"
        gl_account = _first_line_account(record) or _ref_name(getattr(record, "APAccountRef", None))
    elif source_type == "BillPayment":
        vendor = _ref_name(getattr(record, "VendorRef", None)) or "Unknown Vendor"
        bank_ref = getattr(record, "BankAccountRef", None)
        cc_ref = getattr(record, "CreditCardAccountRef", None)
        gl_account = _ref_name(bank_ref) if bank_ref is not None else _ref_name(cc_ref)
    elif source_type == "VendorCredit":
        vendor = _ref_name(getattr(record, "VendorRef", None)) or "Unknown Vendor"
        gl_account = _first_line_account(record)
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


def sync_transactions(
    qb_client: QuickBooks,
    qb_token: Optional[Any] = None,
    realm_id: Optional[str] = None,
) -> dict:
    """Pull QuickBooks records and upsert them into ``Transaction`` (idempotent).

    Idempotency is keyed on ``(realm_id, qb_transaction_id)``: existing rows are
    skipped (not overwritten). ``qb_token`` is passed through to ``pull_raw_records``
    so auth expiry and transient API errors are retried automatically (Prompt 5).
    Returns a counts summary, or one with ``errors=1`` and ``error_message`` when the
    API calls ultimately fail.
    """
    realm_id = realm_id or getattr(qb_token, "realm_id", None) or ""
    company = QuickBooksCompany.objects.for_realm(realm_id)
    try:
        raw = pull_raw_records(qb_client, qb_token=qb_token)
    except Exception as exc:  # noqa: BLE001 — final API failure is reported, not crashed
        logger.exception("sync_quickbooks: failed to pull records from QuickBooks")
        return {
            "created": 0,
            "skipped": 0,
            "errors": 1,
            "per_type": {},
            "error_message": str(exc),
        }
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
            defaults = {
                k: v for k, v in normalized.items() if k != "qb_transaction_id"
            }
            defaults["realm_id"] = realm_id
            defaults["company"] = company
            _obj, was_created = Transaction.objects.get_or_create(
                company=company,
                qb_transaction_id=normalized["qb_transaction_id"],
                defaults=defaults,
            )
            if was_created:
                created += 1
                per_type[source_type]["created"] += 1
            else:
                skipped += 1
                per_type[source_type]["skipped"] += 1

    logger.info("sync_quickbooks: created=%s skipped=%s", created, skipped)
    return {"created": created, "skipped": skipped, "errors": 0, "per_type": per_type}


def fetch_account_current_balances(
    qb_client: QuickBooks,
    qb_token: Optional[Any] = None,
) -> dict[str, dict[str, Any]]:
    """Return current balances for all active QuickBooks accounts.

    Returns a dict keyed by ``account_id`` with values ``{"name": str,
    "balance": Decimal, "account_type": str}``.

    This uses the live ``CurrentBalance`` field on each ``Account`` object, so it
    reflects today's balance rather than a historical month-end balance. It is
    intended as a **sandbox convenience** for seeding ``BankStatementBalance`` rows
    when no statement file is available.
    """

    def _fetch(client: QuickBooks) -> list:
        return Account.all(qb=client)

    try:
        accounts = call_with_retry(qb_client, qb_token, _fetch)
    except Exception as exc:  # noqa: BLE001 — final API failure is reported, not crashed
        logger.exception("fetch_account_current_balances: failed to pull accounts")
        return {}

    balances: dict[str, dict[str, Any]] = {}
    for account in accounts:
        account_id = str(getattr(account, "Id", "") or "")
        name = str(getattr(account, "Name", "") or "")
        if not account_id or not name:
            continue
        balance = _to_decimal(getattr(account, "CurrentBalance", 0))
        account_type = str(getattr(account, "AccountType", "") or "")
        balances[account_id] = {
            "name": name,
            "balance": balance,
            "account_type": account_type,
        }

    return balances


def sync_accounts(
    qb_client: QuickBooks,
    qb_token: Optional[Any] = None,
    realm_id: Optional[str] = None,
) -> dict:
    """Pull the QuickBooks chart of accounts and upsert into ``QBAccount``.

    Idempotency is keyed on ``(company, account_id)``. Existing rows are updated
    so names, types, and active status stay in sync with QBO.
    """
    realm_id = realm_id or getattr(qb_token, "realm_id", None) or ""
    company = QuickBooksCompany.objects.for_realm(realm_id)

    def _fetch(client: QuickBooks) -> list:
        return Account.all(qb=client)

    try:
        accounts = call_with_retry(qb_client, qb_token, _fetch)
    except Exception as exc:  # noqa: BLE001 — final API failure is reported, not crashed
        logger.exception("sync_accounts: failed to pull accounts from QuickBooks")
        return {
            "created": 0,
            "updated": 0,
            "errors": 1,
            "error_message": str(exc),
        }

    created = updated = 0
    for account in accounts:
        account_id = str(getattr(account, "Id", "") or "")
        name = str(getattr(account, "Name", "") or "")
        if not account_id or not name:
            continue

        defaults = {
            "realm_id": realm_id,
            "name": name,
            "account_type": str(getattr(account, "AccountType", "") or ""),
            "account_sub_type": str(getattr(account, "AccountSubType", "") or ""),
            "active": bool(getattr(account, "Active", True)),
        }
        obj, was_created = QBAccount.objects.update_or_create(
            company=company,
            account_id=account_id,
            defaults=defaults,
        )
        if was_created:
            created += 1
        else:
            updated += 1

    logger.info("sync_accounts: created=%s updated=%s", created, updated)
    return {"created": created, "updated": updated, "errors": 0}


def _parse_general_ledger_report(report: Any) -> dict[str, Decimal]:
    """Extract ``{account_name: total_amount}`` from a QuickBooks GeneralLedger report.

    The report structure is deeply nested. This parser is defensive: it walks
    ``Rows.Row`` and ``Rows.Row.Row`` looking for rows whose first ``ColData`` entry
    looks like an account name and whose last numeric ``ColData`` entry can be parsed
    as a monetary amount. Rows without a parseable total are skipped.
    """
    totals: dict[str, Decimal] = {}

    def _rows(node: Any) -> list:
        if node is None:
            return []
        rows = getattr(node, "Row", None)
        if rows is None:
            return []
        return rows if isinstance(rows, list) else [rows]

    def _col_values(row: Any) -> list[str]:
        col_data = getattr(row, "ColData", None)
        if col_data is None:
            return []
        return [str(getattr(col, "Value", "") or "") for col in col_data]

    def _extract_amount(values: list[str]) -> Decimal:
        # Use the last value that parses as a non-zero decimal.
        for value in reversed(values):
            cleaned = value.replace(",", "")
            try:
                amount = Decimal(cleaned)
                if amount != 0:
                    return amount
            except (InvalidOperation, ValueError, TypeError):
                continue
        return Decimal("0")

    def _is_account_name(value: str) -> bool:
        # Account names contain letters; ignore headers and empty cells.
        return bool(value) and any(c.isalpha() for c in value)

    rows = _rows(getattr(report, "Rows", None))
    # Some reports wrap section rows in an outer Row with nested Rows.Row.
    if rows and not _col_values(rows[0]):
        nested = []
        for section in rows:
            nested.extend(_rows(getattr(section, "Rows", None)))
        rows = nested

    for row in rows:
        values = _col_values(row)
        if not values:
            # Try one level deeper (detail rows nested under a summary row).
            for nested_row in _rows(getattr(row, "Rows", None)):
                nested_values = _col_values(nested_row)
                if nested_values and _is_account_name(nested_values[0]):
                    amount = _extract_amount(nested_values)
                    if amount:
                        totals[nested_values[0]] = amount
            continue

        if _is_account_name(values[0]):
            amount = _extract_amount(values)
            if amount:
                totals[values[0]] = amount

    return totals


def fetch_general_ledger_summary(
    qb_client: QuickBooks,
    month: str,
    qb_token: Optional[Any] = None,
) -> dict[str, Decimal]:
    """Fetch month-level account totals from QuickBooks' GeneralLedger report.

    Returns ``{account_name: total_amount}``. Returns an empty dict when the API
    call fails so the close summary can still be drafted without the cross-check.
    """
    from core.common.dates import month_bounds_for_query

    start_date, end_date = month_bounds_for_query(month)

    def _fetch(client: QuickBooks) -> Any:
        return client.get_report(
            "GeneralLedger",
            qs={"start_date": start_date, "end_date": end_date},
        )

    try:
        report = call_with_retry(qb_client, qb_token, _fetch)
    except Exception as exc:  # noqa: BLE001 — report fetch is best-effort
        logger.warning("Failed to fetch GeneralLedger report for %s: %s", month, exc)
        return {}

    return _parse_general_ledger_report(report)