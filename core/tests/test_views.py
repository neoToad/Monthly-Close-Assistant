"""Tests for the QuickBooks OAuth views and ``sync_quickbooks`` command (Prompt 3).

The OAuth start/callback views and the management command are exercised end-to-end
with the QuickBooks network boundaries (``AuthClient``, token exchange/storage, the
``QuickBooks`` client, and ``pull_raw_records``) mocked, so no live sandbox is contacted.
"""
from __future__ import annotations

from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.test import Client, TestCase

from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens


class OAuthStartViewTests(TestCase):
    def test_start_redirects_to_intuit_with_state_in_session(self) -> None:
        with mock.patch.object(qb_client, "make_auth_client") as mock_make:
            auth_client = mock.MagicMock()
            auth_client.get_authorization_url.return_value = (
                "https://appcenter.intuit.com/connect/oauth2?client_id=dummy&state=xyz"
            )
            mock_make.return_value = auth_client

            resp = Client().get("/quickbooks/oauth/start/")

        self.assertEqual(resp.status_code, 302)
        self.assertIn("intuit.com", resp["Location"])
        # A CSRF state is stashed in the session for the callback to verify.
        self.assertIsNotNone(resp.client.session.get("qb_oauth_state"))

    def test_start_handles_misconfiguration(self) -> None:
        # If the QuickBooks client cannot be configured (e.g. empty QB_CLIENT_ID),
        # the start view surfaces an error response rather than a silent redirect.
        with mock.patch.object(qb_client, "make_auth_client", side_effect=ValueError("missing client id")):
            resp = Client().get("/quickbooks/oauth/start/")
        self.assertIn(resp.status_code, (400, 500))


class OAuthCallbackViewTests(TestCase):
    def _session_with_state(self, client: Client, state: str) -> Client:
        session = client.session
        session["qb_oauth_state"] = state
        session.save()
        return client

    def test_callback_exchanges_and_stores_tokens(self) -> None:
        state = "the-state"
        client = self._session_with_state(Client(), state)

        with mock.patch.object(qb_client, "exchange_code_for_tokens") as mock_exchange, \
             mock.patch.object(qb_tokens, "store_tokens") as mock_store:
            # exchange_code_for_tokens returns the populated auth_client-like object.
            exchanged = mock.MagicMock(
                access_token="at", refresh_token="rt", expires_in=3600,
                x_refresh_token_expires_in=8700000, realm_id="123145",
            )
            mock_exchange.return_value = exchanged
            mock_store.return_value = mock.MagicMock()

            resp = client.get(
                "/quickbooks/oauth/callback/",
                {"code": "the-code", "realmId": "123145", "state": state},
            )

        mock_exchange.assert_called_once()
        mock_store.assert_called_once()
        self.assertEqual(resp.status_code, 302)

    def test_callback_rejects_state_mismatch(self) -> None:
        client = self._session_with_state(Client(), "good-state")
        resp = client.get(
            "/quickbooks/oauth/callback/",
            {"code": "c", "realmId": "1", "state": "bad-state"},
        )
        self.assertEqual(resp.status_code, 400)

    def test_callback_requires_code(self) -> None:
        client = self._session_with_state(Client(), "good-state")
        resp = client.get(
            "/quickbooks/oauth/callback/",
            {"realmId": "1", "state": "good-state"},
        )
        self.assertEqual(resp.status_code, 400)


class SyncCommandTests(TestCase):
    def test_no_stored_token_raises_command_error(self) -> None:
        from django.core.management.base import CommandError

        with mock.patch.object(qb_tokens, "get_active_token", return_value=None):
            with self.assertRaises(CommandError):
                call_command("sync_quickbooks", stdout=StringIO())

    def test_command_syncs_and_reports_counts(self) -> None:
        token = mock.MagicMock(realm_id="123145")
        raw = {
            "Purchase": [SimpleNamespace_purchase()],
            "Deposit": [],
            "JournalEntry": [],
        }
        out = StringIO()
        with mock.patch.object(qb_tokens, "get_active_token", return_value=token), \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "pull_raw_records", return_value=raw):
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", stdout=out)

        self.assertIn("created", out.getvalue().lower())
        from core.models import Transaction
        self.assertEqual(Transaction.objects.count(), 1)


def SimpleNamespace_purchase() -> object:
    from types import SimpleNamespace

    def ref(name=""):
        return SimpleNamespace(name=name, value="")

    return SimpleNamespace(
        Id="cmd-1", TxnDate="2026-05-09", TotalAmt="42.00",
        EntityRef=ref("Vendor Co"), AccountRef=ref("Checking"),
        qbo_object_name="Purchase",
    )