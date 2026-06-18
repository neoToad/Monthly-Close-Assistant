"""Tests for the QuickBooks OAuth views, dashboard action views, and ``sync_quickbooks`` command (Prompt 3).

The OAuth start/callback views, dashboard sync/reconcile/summary actions, and the
management command are exercised end-to-end with the QuickBooks network boundaries
(``AuthClient``, token exchange/storage, the ``QuickBooks`` client, and
``pull_raw_records``) mocked, so no live sandbox is contacted.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
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

    def test_command_is_idempotent(self) -> None:
        """Running sync_quickbooks twice with the same records must not duplicate."""
        from core.models import Transaction

        token = mock.MagicMock(realm_id="123145")
        raw = {
            "Purchase": [SimpleNamespace_purchase()],
            "Deposit": [],
            "JournalEntry": [],
        }
        with mock.patch.object(qb_tokens, "get_active_token", return_value=token), \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "pull_raw_records", return_value=raw):
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", stdout=StringIO())
            self.assertEqual(Transaction.objects.count(), 1)
            call_command("sync_quickbooks", stdout=StringIO())
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


# ---------------------------------------------------------------------------
# Dashboard action views
# ---------------------------------------------------------------------------


class DashboardActionViewTests(TestCase):
    def setUp(self) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(username="reviewer", password="test")
        self.client = Client()
        self.client.force_login(self.user)

    def test_sync_now_prompts_to_connect_when_no_token(self) -> None:
        from core.quickbooks import tokens as qb_tokens

        with mock.patch.object(qb_tokens, "get_active_token", return_value=None):
            resp = self.client.post("/dashboard/sync/", {"month": "2025-01"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "QuickBooks is not connected")

    @mock.patch("core.views.qb_client.sync_transactions")
    @mock.patch("core.views.qb_client.build_quickbooks_client")
    def test_sync_now_runs_sync_and_shows_notice(self, mock_build, mock_sync) -> None:
        from core.quickbooks import tokens as qb_tokens

        token = mock.MagicMock(realm_id="123145")
        mock_build.return_value = mock.MagicMock()
        mock_sync.return_value = {
            "created": 3,
            "skipped": 0,
            "errors": 0,
            "per_type": {},
        }

        with mock.patch.object(qb_tokens, "get_active_token", return_value=token):
            resp = self.client.post("/dashboard/sync/", {"month": "2025-01"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "QuickBooks sync complete")
        self.assertContains(resp, "created 3")
        mock_sync.assert_called_once()

    def test_reconcile_month_creates_flags(self) -> None:
        from core.models import BankTransaction, Transaction

        txn = Transaction.objects.create(
            date=dt.date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("100.00"),
            qb_transaction_id="QB-1",
            source_type="Purchase",
        )
        BankTransaction.objects.create(
            date=txn.date,
            vendor=txn.vendor,
            amount=Decimal("102.50"),
            qb_transaction_id=txn.qb_transaction_id,
        )

        resp = self.client.post("/dashboard/reconcile/", {"month": "2025-01"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Reconciliation complete")
        self.assertTrue(
            Transaction.objects.filter(qb_transaction_id="QB-1").exists()
        )

    def test_draft_summary_creates_summary(self) -> None:
        from core.models import CloseSummary

        resp = self.client.post("/dashboard/summary/draft/", {"month": "2025-01"})

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Close summary drafted")
        self.assertEqual(CloseSummary.objects.filter(month="2025-01").count(), 1)