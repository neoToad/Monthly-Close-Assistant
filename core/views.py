"""Views for the QuickBooks OAuth flow (Prompt 3).

Two endpoints wire the Intuit OAuth 2.0 authorization-code flow:

* ``qb_oauth_start`` — redirects the user to Intuit's authorize URL (a CSRF state
  is stashed in the session for the callback to verify).
* ``qb_oauth_callback`` — receives the code + realmId, verifies the state, exchanges
  the code for tokens, and persists them encrypted (see ``core.quickbooks.tokens``).

The network boundaries (``make_auth_client``, ``exchange_code_for_tokens``,
``store_tokens``) are imported from ``core.quickbooks`` so they can be mocked in tests.
"""
from __future__ import annotations

from django.http import HttpResponseBadRequest, HttpResponseRedirect
from django.views.decorators.http import require_http_methods

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