"""At-rest token encryption and persistence for QuickBooks OAuth tokens (Prompt 3).

Access/refresh tokens are sensitive: they are encrypted with a Fernet symmetric
key before being written to the ``QBToken`` table. The key is read from the
``QB_TOKEN_ENCRYPTION_KEY`` setting (sourced from the environment via
``.env``). When that key is not configured, values pass through in plaintext so
local development works without provisioning a key — a warning is emitted each
time, and the ``QBToken`` fields then literally hold the plaintext token.

``cryptography`` is already installed (a transitive dependency of the Intuit /
QuickBooks libraries).
"""
from __future__ import annotations

import warnings
from datetime import timedelta
from typing import Any, Optional

from cryptography.fernet import Fernet, InvalidToken
from django.conf import settings
from django.utils import timezone


def _build_fernet(key: Optional[bytes | str] = None) -> Optional[Fernet]:
    """Return a Fernet cipher from an explicit key, else from settings, else None."""
    if key is not None:
        raw = key.encode() if isinstance(key, str) else key
        return Fernet(raw)
    setting = getattr(settings, "QB_TOKEN_ENCRYPTION_KEY", "") or ""
    if not setting:
        return None
    return Fernet(setting.encode())


def encrypt_value(plaintext: str, key: Optional[bytes | str] = None) -> str:
    """Encrypt ``plaintext``; passthrough (with a warning) when no key is set."""
    fernet = _build_fernet(key)
    if fernet is None:
        warnings.warn(
            "QB_TOKEN_ENCRYPTION_KEY is not set; storing QuickBooks tokens in "
            "plaintext. Configure a Fernet key for any non-local environment.",
            stacklevel=2,
        )
        return plaintext
    return fernet.encrypt(plaintext.encode("utf-8")).decode("utf-8")


def decrypt_value(ciphertext: str, key: Optional[bytes | str] = None) -> str:
    """Decrypt ``ciphertext``; passthrough when no key is set or it isn't a Fernet token."""
    fernet = _build_fernet(key)
    if fernet is None:
        return ciphertext
    try:
        return fernet.decrypt(ciphertext.encode("utf-8")).decode("utf-8")
    except InvalidToken:
        # Tolerates a value written under a no-key (plaintext) session.
        return ciphertext


def _expiry(now: Any, seconds: Optional[int]):
    """Return ``now + seconds`` as an aware datetime, or ``None`` when seconds is falsy."""
    if seconds is None:
        return None
    return now + timedelta(seconds=int(seconds))


def store_tokens(auth_client: Any, realm_id: Optional[str] = None):
    """Persist the access/refresh tokens carried on an ``AuthClient`` to ``QBToken``.

    ``auth_client`` is an Intuit ``AuthClient`` (or a mock with the same attributes)
    that has just exchanged a code or refreshed. Tokens are encrypted at rest and
    the row is upserted on ``realm_id`` (the QuickBooks company id). Also creates or
    updates the corresponding ``QuickBooksCompany`` record.
    """
    from core.models import QBToken, QuickBooksCompany

    realm_id = realm_id or getattr(auth_client, "realm_id", None) or ""
    now = timezone.now()
    defaults = {
        "access_token_encrypted": encrypt_value(getattr(auth_client, "access_token", "") or ""),
        "refresh_token_encrypted": encrypt_value(getattr(auth_client, "refresh_token", "") or ""),
        "access_token_expires_at": _expiry(now, getattr(auth_client, "expires_in", None)),
        "refresh_token_expires_at": _expiry(
            now, getattr(auth_client, "x_refresh_token_expires_in", None)
        ),
        "last_refreshed": now,
    }
    token, _created = QBToken.objects.update_or_create(
        realm_id=realm_id, defaults=defaults
    )
    QuickBooksCompany.objects.update_or_create(
        realm_id=realm_id,
        defaults={"is_connected": True},
    )
    return token


def get_active_token(realm_id: Optional[str] = None):
    """Return the stored token for ``realm_id`` (or the most-recently refreshed one)."""
    from core.models import QBToken

    if realm_id:
        return QBToken.objects.filter(realm_id=realm_id).first()
    return QBToken.objects.order_by("-updated_at").first()


def get_active_tokens():
    """Return all stored QuickBooks tokens (one per connected realm)."""
    from core.models import QBToken

    return QBToken.objects.order_by("-updated_at")