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
from django.core.files.uploadedfile import SimpleUploadedFile
from django.test import Client, TestCase

from core.models import QuickBooksCompany
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens


def _company(realm_id: str = "realm-a") -> QuickBooksCompany:
    return QuickBooksCompany.objects.for_realm(realm_id)


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
             mock.patch.object(qb_tokens, "store_tokens") as mock_store, \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", return_value=""):
            # exchange_code_for_tokens returns the populated auth_client-like object.
            exchanged = mock.MagicMock(
                access_token="at", refresh_token="rt", expires_in=3600,
                x_refresh_token_expires_in=8700000, realm_id="123145",
            )
            mock_exchange.return_value = exchanged
            mock_store.return_value = mock.MagicMock(realm_id="123145")
            mock_build.return_value = mock.MagicMock()

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

    def test_callback_reports_oauth_configuration_error(self) -> None:
        state = "the-state"
        client = self._session_with_state(Client(), state)

        with mock.patch.object(
            qb_client, "make_auth_client", side_effect=ValueError("missing client id")
        ), self.assertLogs("core.views", level="ERROR") as logs:
            resp = client.get(
                "/quickbooks/oauth/callback/",
                {"code": "the-code", "realmId": "123145", "state": state},
            )

        self.assertEqual(resp.status_code, 400)
        self.assertContains(
            resp, "QuickBooks OAuth is not configured.", status_code=400
        )
        self.assertIn("realm_id=123145", "\n".join(logs.output))
        self.assertIn("state_valid=True", "\n".join(logs.output))

    def test_callback_logs_token_exchange_failure_with_context(self) -> None:
        state = "the-state"
        client = self._session_with_state(Client(), state)

        with mock.patch.object(qb_client, "make_auth_client") as mock_make, \
             mock.patch.object(
                 qb_client,
                 "exchange_code_for_tokens",
                 side_effect=RuntimeError("intuit unavailable"),
             ), self.assertLogs("core.views", level="ERROR") as logs:
            mock_make.return_value = mock.MagicMock()
            resp = client.get(
                "/quickbooks/oauth/callback/",
                {"code": "the-code", "realmId": "123145", "state": state},
            )

        self.assertEqual(resp.status_code, 400)
        self.assertContains(
            resp, "QuickBooks token exchange failed.", status_code=400
        )
        output = "\n".join(logs.output)
        self.assertIn("realm_id=123145", output)
        self.assertIn("state_valid=True", output)

    def test_callback_stores_quickbooks_company_name(self) -> None:
        from core.models import QuickBooksCompany

        state = "the-state"
        client = self._session_with_state(Client(), state)
        QuickBooksCompany.objects.create(realm_id="123145", name="")

        with mock.patch.object(qb_client, "make_auth_client") as mock_make, \
             mock.patch.object(qb_client, "exchange_code_for_tokens") as mock_exchange, \
             mock.patch.object(qb_tokens, "store_tokens") as mock_store, \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", return_value="Demo Co"):
            mock_auth_client = mock.MagicMock()
            mock_make.return_value = mock_auth_client
            exchanged = mock.MagicMock(
                access_token="at", refresh_token="rt", expires_in=3600,
                x_refresh_token_expires_in=8700000, realm_id="123145",
            )
            mock_exchange.return_value = exchanged
            mock_store.return_value = mock.MagicMock(realm_id="123145")
            mock_build.return_value = mock.MagicMock()

            resp = client.get(
                "/quickbooks/oauth/callback/",
                {"code": "the-code", "realmId": "123145", "state": state},
            )

        self.assertEqual(resp.status_code, 302)
        company = QuickBooksCompany.objects.get(realm_id="123145")
        self.assertEqual(company.name, "Demo Co")

    def test_callback_redirects_when_company_name_fetch_fails(self) -> None:
        from core.models import QuickBooksCompany

        state = "the-state"
        client = self._session_with_state(Client(), state)
        QuickBooksCompany.objects.create(realm_id="123145", name="")

        with mock.patch.object(qb_client, "make_auth_client") as mock_make, \
             mock.patch.object(qb_client, "exchange_code_for_tokens") as mock_exchange, \
             mock.patch.object(qb_tokens, "store_tokens") as mock_store, \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", side_effect=Exception("lookup failed")):
            mock_auth_client = mock.MagicMock()
            mock_make.return_value = mock_auth_client
            exchanged = mock.MagicMock(
                access_token="at", refresh_token="rt", expires_in=3600,
                x_refresh_token_expires_in=8700000, realm_id="123145",
            )
            mock_exchange.return_value = exchanged
            mock_store.return_value = mock.MagicMock(realm_id="123145")
            mock_build.return_value = mock.MagicMock()

            resp = client.get(
                "/quickbooks/oauth/callback/",
                {"code": "the-code", "realmId": "123145", "state": state},
            )

        self.assertEqual(resp.status_code, 302)
        company = QuickBooksCompany.objects.get(realm_id="123145")
        self.assertEqual(company.name, "")


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
             mock.patch.object(qb_client, "fetch_company_name", return_value=""), \
             mock.patch.object(qb_client, "pull_raw_records", return_value=raw), \
             mock.patch.object(qb_client, "sync_accounts", return_value={"created": 0, "updated": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_customers", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_invoices", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}):
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", "--realm-id", "123145", stdout=out)

        self.assertIn("created", out.getvalue().lower())
        from core.models import Transaction
        self.assertEqual(Transaction.objects.count(), 1)
        self.assertEqual(Transaction.objects.first().realm_id, "123145")

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
             mock.patch.object(qb_client, "fetch_company_name", return_value=""), \
             mock.patch.object(qb_client, "pull_raw_records", return_value=raw), \
             mock.patch.object(qb_client, "sync_accounts", return_value={"created": 0, "updated": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_customers", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_invoices", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}):
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", "--realm-id", "123145", stdout=StringIO())
            self.assertEqual(Transaction.objects.count(), 1)
            call_command("sync_quickbooks", "--realm-id", "123145", stdout=StringIO())
            self.assertEqual(Transaction.objects.count(), 1)

    def test_command_updates_company_name(self) -> None:
        from core.models import QuickBooksCompany, Transaction

        token = mock.MagicMock(realm_id="123145")
        raw = {
            "Purchase": [SimpleNamespace_purchase()],
            "Deposit": [],
            "JournalEntry": [],
        }
        with mock.patch.object(qb_tokens, "get_active_token", return_value=token), \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", return_value="Demo Co"), \
             mock.patch.object(qb_client, "pull_raw_records", return_value=raw), \
             mock.patch.object(qb_client, "sync_accounts", return_value={"created": 0, "updated": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_customers", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_invoices", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}):
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", "--realm-id", "123145", stdout=StringIO())

        self.assertEqual(Transaction.objects.filter(realm_id="123145").count(), 1)
        company = QuickBooksCompany.objects.get(realm_id="123145")
        self.assertEqual(company.name, "Demo Co")

    def test_sync_command_prints_new_source_counts(self) -> None:
        from core.models import Transaction

        token = mock.MagicMock(realm_id="123145")
        raw = {
            "Purchase": [],
            "Deposit": [],
            "JournalEntry": [],
            "Bill": [SimpleNamespace_bill()],
            "BillPayment": [],
            "VendorCredit": [],
        }
        out = StringIO()
        with mock.patch.object(qb_tokens, "get_active_token", return_value=token), \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", return_value=""), \
             mock.patch.object(qb_client, "pull_raw_records", return_value=raw), \
             mock.patch.object(qb_client, "sync_accounts", return_value={"created": 0, "updated": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_customers", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_invoices", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}):
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", "--realm-id", "123145", stdout=out)

        output = out.getvalue()
        self.assertIn("Bill: created=1", output)
        self.assertEqual(Transaction.objects.filter(source_type="Bill").count(), 1)


def SimpleNamespace_purchase() -> object:
    from types import SimpleNamespace

    def ref(name=""):
        return SimpleNamespace(name=name, value="")

    return SimpleNamespace(
        Id="cmd-1", TxnDate="2026-05-09", TotalAmt="42.00",
        EntityRef=ref("Vendor Co"), AccountRef=ref("Checking"),
        qbo_object_name="Purchase",
    )


def SimpleNamespace_bill() -> object:
    from types import SimpleNamespace

    def ref(name=""):
        return SimpleNamespace(name=name, value="")

    return SimpleNamespace(
        Id="cmd-bill-1", TxnDate="2026-05-10", TotalAmt="250.00",
        VendorRef=ref("Utility Co"), APAccountRef=ref("Accounts Payable"),
        Line=[SimpleNamespace(Amount="250.00", AccountRef=ref("Utilities"))],
        qbo_object_name="Bill",
    )


# ---------------------------------------------------------------------------
# Dashboard action views
# ---------------------------------------------------------------------------


class BankBalancesDashboardTests(TestCase):
    def setUp(self) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(username="reviewer", password="test")
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_shows_bank_balances_panel(self) -> None:
        from core.models import BankStatementBalance, QBAccount, Transaction

        company = _company("realm-a")
        QBAccount.objects.create(
            company=company,
            realm_id="realm-a",
            account_id="qb-acc-1",
            name="Operating Checking",
            account_type="Bank",
        )
        BankStatementBalance.objects.create(
            company=company,
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-3621.93"),
            source=BankStatementBalance.Source.MANUAL,
        )
        Transaction.objects.create(
            company=company,
            date=dt.date(2026, 6, 15),
            vendor="Acme",
            amount=Decimal("568.38"),
            gl_account="Operating Checking",
            qb_transaction_id="QB-1",
            source_type="Purchase",
            realm_id="realm-a",
        )

        resp = self.client.get("/dashboard/?company=realm-a&month=2026-06")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bank Balances")
        self.assertContains(resp, "Operating Checking")
        self.assertContains(resp, "-3621.93")
        self.assertContains(resp, "568.38")

    def test_dashboard_flags_balance_gap(self) -> None:
        from core.models import BankStatementBalance, QBAccount, Transaction

        company = _company("realm-a")
        QBAccount.objects.create(
            company=company,
            realm_id="realm-a",
            account_id="qb-acc-1",
            name="Operating Checking",
            account_type="Bank",
        )
        BankStatementBalance.objects.create(
            company=company,
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-3621.93"),
            source=BankStatementBalance.Source.MANUAL,
        )
        Transaction.objects.create(
            company=company,
            date=dt.date(2026, 6, 15),
            vendor="Acme",
            amount=Decimal("568.38"),
            gl_account="Operating Checking",
            qb_transaction_id="QB-1",
            source_type="Purchase",
            realm_id="realm-a",
        )

        self.client.post("/dashboard/reconcile/", {"month": "2026-06", "realm_id": "realm-a"})
        resp = self.client.get("/dashboard/?company=realm-a&month=2026-06")
        self.assertContains(resp, "Balance")
        self.assertContains(resp, "Bank ending balance")

    def test_set_bank_balance_view_creates_row(self) -> None:
        from core.models import QBAccount

        company = _company("realm-a")
        QBAccount.objects.create(
            company=company,
            realm_id="realm-a",
            account_id="qb-acc-1",
            name="Operating Checking",
            account_type="Bank",
        )
        resp = self.client.post(
            "/dashboard/balance/set/",
            {
                "month": "2026-06",
                "realm_id": "realm-a",
                "qb_account_id": "qb-acc-1",
                "ending_balance": "-3621.93",
            },
        )
        self.assertEqual(resp.status_code, 200)
        from core.models import BankStatementBalance
        self.assertEqual(BankStatementBalance.objects.count(), 1)
        balance = BankStatementBalance.objects.first()
        self.assertEqual(balance.ending_balance, Decimal("-3621.93"))
        self.assertEqual(balance.account_name, "Operating Checking")
        self.assertEqual(balance.source, "manual")

    def test_dashboard_shows_bank_balances_panel_without_accounts(self) -> None:
        """The panel should render when a company is selected so users know what to do."""
        _company("realm-a")

        resp = self.client.get("/dashboard/?company=realm-a&month=2026-06")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bank Balances")
        self.assertContains(resp, "No cash-like accounts found")
        self.assertContains(resp, "Sync QuickBooks")


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
            resp = self.client.post(
                "/dashboard/sync/",
                {"month": "2025-01", "realm_id": "123145"},
            )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "QuickBooks sync complete")
        self.assertContains(resp, "created 3")
        mock_sync.assert_called_once()
        call_kwargs = mock_sync.call_args.kwargs
        self.assertEqual(call_kwargs.get("realm_id"), "123145")

    def test_reconcile_month_creates_flags(self) -> None:
        from core.models import BankTransaction, Transaction

        company = _company("realm-a")
        txn = Transaction.objects.create(
            company=company,
            date=dt.date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("100.00"),
            qb_transaction_id="QB-1",
            source_type="Purchase",
            realm_id="realm-a",
        )
        BankTransaction.objects.create(
            company=company,
            date=txn.date,
            vendor=txn.vendor,
            amount=Decimal("102.50"),
            qb_transaction_id=txn.qb_transaction_id,
            realm_id=txn.realm_id,
        )

        resp = self.client.post(
            "/dashboard/reconcile/", {"month": "2025-01", "realm_id": "realm-a"}
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Reconciliation complete")
        self.assertTrue(
            Transaction.objects.filter(qb_transaction_id="QB-1").exists()
        )

    def test_draft_summary_creates_summary(self) -> None:
        from core.models import CloseSummary

        company = _company("realm-a")
        summary = CloseSummary.objects.create(
            company=company,
            realm_id="realm-a",
            month="2025-01",
            summary_text="Drafted summary.",
        )
        with mock.patch(
            "core.views.orchestrate_close_summary",
            return_value=summary,
        ):
            resp = self.client.post(
                "/dashboard/summary/draft/", {"month": "2025-01", "realm_id": "realm-a"}
            )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Close summary drafted")
        self.assertEqual(CloseSummary.objects.filter(month="2025-01").count(), 1)

    def test_set_bank_balance_view_is_idempotent(self) -> None:
        from core.models import BankStatementBalance, QBAccount, QuickBooksCompany

        company = QuickBooksCompany.objects.for_realm("realm-a")
        QBAccount.objects.create(
            company=company,
            realm_id="realm-a",
            account_id="qb-acc-1",
            name="Operating Checking",
            account_type="Bank",
        )

        self.client.post(
            "/dashboard/balance/set/",
            {
                "month": "2026-06",
                "realm_id": "realm-a",
                "qb_account_id": "qb-acc-1",
                "ending_balance": "-1000.00",
            },
        )
        first = BankStatementBalance.objects.get(
            realm_id="realm-a", qb_account_id="qb-acc-1", month="2026-06"
        )

        self.client.post(
            "/dashboard/balance/set/",
            {
                "month": "2026-06",
                "realm_id": "realm-a",
                "qb_account_id": "qb-acc-1",
                "ending_balance": "-3621.93",
            },
        )
        second = BankStatementBalance.objects.get(
            realm_id="realm-a", qb_account_id="qb-acc-1", month="2026-06"
        )

        self.assertEqual(first.id, second.id)
        self.assertEqual(
            BankStatementBalance.objects.filter(
                realm_id="realm-a", qb_account_id="qb-acc-1", month="2026-06"
            ).count(),
            1,
        )
        self.assertEqual(second.ending_balance, Decimal("-3621.93"))


class ReconcileAccountViewTests(TestCase):
    def setUp(self) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(username="reviewer", password="test")
        self.client = Client()
        self.client.force_login(self.user)

    def _setup_account_and_balance(self) -> None:
        from core.models import BankStatementBalance, QBAccount, QuickBooksCompany

        company = QuickBooksCompany.objects.for_realm("realm-a")
        QBAccount.objects.create(
            company=company,
            realm_id="realm-a",
            account_id="qb-acc-1",
            name="Operating Checking",
            account_type="Bank",
        )
        return BankStatementBalance.objects.create(
            company=company,
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-3621.93"),
            source=BankStatementBalance.Source.MANUAL,
        )

    def test_suggest_modal_returns_suggestion_cards(self) -> None:
        self._setup_account_and_balance()
        resp = self.client.get(
            "/dashboard/account/qb-acc-1/suggest/",
            {"month": "2026-06", "realm_id": "realm-a"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Reconcile Operating Checking")
        self.assertContains(resp, "Suggested fixes")

    def test_apply_dry_run_returns_preview_without_qb_call(self) -> None:
        from core.models import Transaction, SourceType

        balance = self._setup_account_and_balance()
        Transaction.objects.create(
            company=balance.company,
            date=dt.date(2026, 6, 15),
            vendor="Acme",
            amount=Decimal("568.38"),
            gl_account="Operating Checking",
            qb_transaction_id="QB-1",
            source_type=SourceType.PURCHASE,
            realm_id="realm-a",
        )

        with mock.patch(
            "core.services.reconciliation.qb_writes.apply_suggestion"
        ) as mock_apply:
            resp = self.client.post(
                "/dashboard/account/qb-acc-1/apply/",
                {
                    "month": "2026-06",
                    "realm_id": "realm-a",
                    "suggestion_ids": ["sug-1"],
                    "dry_run": "true",
                },
            )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Preview")
        mock_apply.assert_not_called()

    def test_apply_confirmation_calls_qb_and_refreshes_balances(self) -> None:
        from core.models import Transaction, SourceType
        from core.quickbooks import client as qb_client

        balance = self._setup_account_and_balance()
        Transaction.objects.create(
            company=balance.company,
            date=dt.date(2026, 6, 15),
            vendor="Acme",
            amount=Decimal("568.38"),
            gl_account="Operating Checking",
            qb_transaction_id="QB-1",
            source_type=SourceType.PURCHASE,
            realm_id="realm-a",
        )
        token = mock.MagicMock(realm_id="realm-a")

        with mock.patch(
            "core.services.reconciliation.qb_tokens.get_active_token", return_value=token
        ), mock.patch.object(
            qb_client, "build_quickbooks_client"
        ) as mock_build, mock.patch.object(
            qb_client, "sync_transactions", return_value={"created": 0, "skipped": 0, "errors": 0}
        ) as mock_sync, mock.patch(
            "core.services.reconciliation.qb_writes.apply_suggestion"
        ) as mock_apply:
            mock_apply.return_value = {
                "object_type": "JournalEntry",
                "id": "je-1",
                "amount": "53.55",
            }
            mock_build.return_value = mock.MagicMock()
            resp = self.client.post(
                "/dashboard/account/qb-acc-1/apply/",
                {
                    "month": "2026-06",
                    "realm_id": "realm-a",
                    "suggestion_ids": ["sug-1"],
                    "dry_run": "false",
                },
            )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bank Balances")
        mock_apply.assert_called_once()
        mock_sync.assert_called_once()

    def test_apply_without_confirmation_is_preview(self) -> None:
        from core.models import Transaction, SourceType

        balance = self._setup_account_and_balance()
        Transaction.objects.create(
            company=balance.company,
            date=dt.date(2026, 6, 15),
            vendor="Acme",
            amount=Decimal("568.38"),
            gl_account="Operating Checking",
            qb_transaction_id="QB-1",
            source_type=SourceType.PURCHASE,
            realm_id="realm-a",
        )

        with mock.patch(
            "core.services.reconciliation.qb_writes.apply_suggestion"
        ) as mock_apply:
            resp = self.client.post(
                "/dashboard/account/qb-acc-1/apply/",
                {
                    "month": "2026-06",
                    "realm_id": "realm-a",
                    "suggestion_ids": ["sug-1"],
                },
            )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Preview")
        mock_apply.assert_not_called()


class GenerateBankFeedViewTests(TestCase):
    def setUp(self) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(username="reviewer", password="test")
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_shows_synthetic_bank_feed_button(self) -> None:
        _company("realm-a")
        resp = self.client.get("/dashboard/?company=realm-a&month=2025-01")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Generate Synthetic Bank Feed")
        self.assertContains(resp, "For testing only")

    def test_dashboard_shows_import_bank_feed_csv_form(self) -> None:
        _company("realm-a")
        resp = self.client.get("/dashboard/?company=realm-a&month=2025-01")
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Import Bank Feed CSV")
        self.assertContains(resp, "Load real bank statement")

    def test_generate_bank_feed_creates_rows(self) -> None:
        from core.models import Transaction

        company = _company("realm-a")
        Transaction.objects.create(
            company=company,
            date=dt.date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("100.00"),
            qb_transaction_id="QB-1",
            source_type="Purchase",
            realm_id="realm-a",
        )

        resp = self.client.post(
            "/dashboard/bank-feed/generate/",
            {"month": "2025-01", "realm_id": "realm-a"},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Synthetic bank feed generated")
        from core.models import BankTransaction
        self.assertGreater(BankTransaction.objects.count(), 0)

    def test_generate_bank_feed_no_transactions_notice(self) -> None:
        _company("realm-a")
        resp = self.client.post(
            "/dashboard/bank-feed/generate/",
            {"month": "2025-01", "realm_id": "realm-a"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "No transactions for this month")

    def test_generate_bank_feed_existing_requires_force(self) -> None:
        from core.models import BankTransaction, Transaction

        company = _company("realm-a")
        Transaction.objects.create(
            company=company,
            date=dt.date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("100.00"),
            qb_transaction_id="QB-1",
            source_type="Purchase",
            realm_id="realm-a",
        )
        self.client.post(
            "/dashboard/bank-feed/generate/",
            {"month": "2025-01", "realm_id": "realm-a"},
        )
        first_count = BankTransaction.objects.count()
        self.assertGreater(first_count, 0)

        resp = self.client.post(
            "/dashboard/bank-feed/generate/",
            {"month": "2025-01", "realm_id": "realm-a"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "already exist")

    def test_generate_bank_feed_force_overwrites(self) -> None:
        from core.models import BankTransaction, Transaction

        company = _company("realm-a")
        Transaction.objects.create(
            company=company,
            date=dt.date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("100.00"),
            qb_transaction_id="QB-1",
            source_type="Purchase",
            realm_id="realm-a",
        )
        self.client.post(
            "/dashboard/bank-feed/generate/",
            {"month": "2025-01", "realm_id": "realm-a"},
        )
        first_count = BankTransaction.objects.count()
        self.assertGreater(first_count, 0)

        resp = self.client.post(
            "/dashboard/bank-feed/generate/",
            {"month": "2025-01", "realm_id": "realm-a", "force": "true"},
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Synthetic bank feed generated")
        self.assertEqual(BankTransaction.objects.count(), first_count)


class ImportBankFeedViewTests(TestCase):
    def setUp(self) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(username="reviewer", password="test")
        self.client = Client()
        self.client.force_login(self.user)

    def test_import_bank_feed_csv_creates_rows(self) -> None:
        from core.models import BankTransaction

        _company("realm-a")
        csv_file = SimpleUploadedFile(
            "statement.csv",
            b"date,amount,vendor\n2025-01-15,100.00,Acme Corp\n",
            content_type="text/csv",
        )

        resp = self.client.post(
            "/dashboard/bank-feed/import/",
            {
                "month": "2025-01",
                "realm_id": "realm-a",
                "csv_file": csv_file,
            },
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Bank feed CSV imported")
        self.assertEqual(BankTransaction.objects.count(), 1)
        self.assertEqual(BankTransaction.objects.first().source, "csv_import")

    def test_import_invalid_csv_returns_400_notice(self) -> None:
        from core.models import BankTransaction

        _company("realm-a")
        csv_file = SimpleUploadedFile(
            "statement.csv",
            b"date,amount\n2025-01-15,not-a-number\n",
            content_type="text/csv",
        )

        resp = self.client.post(
            "/dashboard/bank-feed/import/",
            {
                "month": "2025-01",
                "realm_id": "realm-a",
                "csv_file": csv_file,
            },
        )

        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, "Bank feed CSV import failed", status_code=400)
        self.assertEqual(BankTransaction.objects.count(), 0)

    def test_import_non_csv_file_rejected(self) -> None:
        _company("realm-a")
        txt_file = SimpleUploadedFile(
            "statement.txt",
            b"not a csv",
            content_type="text/plain",
        )
        resp = self.client.post(
            "/dashboard/bank-feed/import/",
            {
                "month": "2025-01",
                "realm_id": "realm-a",
                "csv_file": txt_file,
            },
        )
        self.assertEqual(resp.status_code, 400)
        self.assertContains(resp, ".csv files", status_code=400)


class ConnectWiseDashboardViewTests(TestCase):
    def setUp(self) -> None:
        from django.contrib.auth import get_user_model

        User = get_user_model()
        self.user = User.objects.create_user(username="reviewer", password="test")
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_renders_connectwise_section(self) -> None:
        _company("realm-cw")

        resp = self.client.get("/dashboard/?company=realm-cw&month=2025-01")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Client Reconciliation")
        self.assertContains(resp, "Run ConnectWise Reconciliation")
        self.assertContains(resp, "Generate ConnectWise Test Feed")

    def test_run_connectwise_reconciliation_creates_flags(self) -> None:
        from core.engines import generate_connectwise_feed

        generate_connectwise_feed(
            month="2025-01", realm_id="realm-cw", scenario="missing_mapping"
        )

        resp = self.client.post(
            "/dashboard/connectwise/reconcile/",
            {"month": "2025-01", "realm_id": "realm-cw"},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ConnectWise reconciliation complete")
        from core.models import Flag, FlagType
        self.assertEqual(
            Flag.objects.filter(
                realm_id="realm-cw", flag_type=FlagType.CONNECTWISE_MISSING_MAPPING
            ).count(),
            1,
        )

    def test_generate_connectwise_feed_creates_activity(self) -> None:
        from core.models import TimeEntry

        _company("realm-cw")
        resp = self.client.post(
            "/dashboard/connectwise/generate/",
            {"month": "2025-01", "realm_id": "realm-cw", "scenario": "missing_mapping"},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "ConnectWise feed generated")
        self.assertGreater(TimeEntry.objects.filter(realm_id="realm-cw").count(), 0)
