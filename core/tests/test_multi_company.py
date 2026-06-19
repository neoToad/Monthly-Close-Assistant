"""Behavior tests for multi-company QuickBooks realm isolation.

Verifies that reconciliation, anomaly detection, bank feed generation, close
summary drafting, and dashboard views keep transactions/flags/bank rows/summaries
separate across realms.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import StringIO
from types import SimpleNamespace
from unittest import mock

from django.contrib.auth import get_user_model
from django.core.management import call_command
from django.test import Client, TestCase

from core.agent.summary import draft_close_summary, gather_inputs
from core.anomaly.rules import run_anomaly_detection
from core.bank_feed import generate_bank_feed
from core.models import (
    BankTransaction,
    CloseSummary,
    Flag,
    FlagType,
    QBAccount,
    QBToken,
    QuickBooksCompany,
    Severity,
    SourceType,
    Transaction,
)
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens
from core.reconciliation.engine import run_reconciliation

User = get_user_model()


def _make_txn(realm_id: str = "realm-a", **overrides) -> Transaction:
    defaults = dict(
        date=dt.date(2025, 1, 15),
        vendor="Acme Corp",
        amount=Decimal("100.00"),
        category="Office Supplies",
        gl_account="5000 - Supplies",
        qb_transaction_id="QB-1",
        source_type=SourceType.PURCHASE,
        realm_id=realm_id,
    )
    defaults.update(overrides)
    return Transaction.objects.create(**defaults)


def _make_bank_txn(realm_id: str = "realm-a", **overrides) -> BankTransaction:
    defaults = dict(
        date=dt.date(2025, 1, 15),
        vendor="Acme Corp",
        amount=Decimal("100.00"),
        category="Office Supplies",
        gl_account="5000 - Supplies",
        qb_transaction_id="QB-1",
        source_type=SourceType.PURCHASE,
        realm_id=realm_id,
    )
    defaults.update(overrides)
    return BankTransaction.objects.create(**defaults)


def _config_patch() -> mock._patch:
    """Return a patch forcing deterministic close-summary path."""
    config_values = {
        "CLOSE_SUMMARY_PROVIDER": "anthropic",
        "ANTHROPIC_API_KEY": "",
        "OPENAI_API_KEY": "",
        "CLOSE_SUMMARY_MODEL": "claude-sonnet-4-6",
    }
    return mock.patch(
        "core.agent.summary.config",
        side_effect=lambda key, default="": config_values.get(key, default),
    )


class RealmIsolationReconciliationTests(TestCase):
    def test_reconciliation_only_creates_flags_for_target_realm(self) -> None:
        txn_a = _make_txn(realm_id="realm-a", qb_transaction_id="QB-A")
        _make_bank_txn(realm_id="realm-a", qb_transaction_id="QB-A", amount=Decimal("105.00"))
        _make_txn(realm_id="realm-b", qb_transaction_id="QB-B")
        _make_bank_txn(realm_id="realm-b", qb_transaction_id="QB-B", amount=Decimal("205.00"))

        result = run_reconciliation("2025-01", realm_id="realm-a")

        self.assertEqual(result["flags_created"], 1)
        self.assertEqual(Flag.objects.filter(realm_id="realm-a").count(), 1)
        self.assertEqual(Flag.objects.filter(realm_id="realm-b").count(), 0)

    def test_reconciliation_deletes_only_target_realm_flags(self) -> None:
        txn_a = _make_txn(realm_id="realm-a", qb_transaction_id="QB-A")
        _make_bank_txn(realm_id="realm-a", qb_transaction_id="QB-A", amount=Decimal("100.00"))
        Flag.objects.create(
            realm_id="realm-a",
            flag_type=FlagType.RECONCILIATION,
            transaction=txn_a,
            reason="old flag",
            severity=Severity.MEDIUM,
        )
        txn_b = _make_txn(realm_id="realm-b", qb_transaction_id="QB-B")
        Flag.objects.create(
            realm_id="realm-b",
            flag_type=FlagType.RECONCILIATION,
            transaction=txn_b,
            reason="other realm flag",
            severity=Severity.MEDIUM,
        )

        run_reconciliation("2025-01", realm_id="realm-a")

        self.assertFalse(Flag.objects.filter(realm_id="realm-a").exists())
        self.assertTrue(Flag.objects.filter(realm_id="realm-b").exists())


class RealmIsolationAnomalyTests(TestCase):
    def test_anomaly_detection_only_flags_target_realm(self) -> None:
        # Two realms, same vendor, same month. New-vendor anomaly should only fire
        # for the realm whose data is being inspected.
        _make_txn(realm_id="realm-a", qb_transaction_id="QB-A", vendor="New Vendor")
        _make_txn(realm_id="realm-b", qb_transaction_id="QB-B", vendor="New Vendor")

        result = run_anomaly_detection("2025-01", realm_id="realm-a")

        self.assertEqual(result["anomaly_flags_created"], 1)
        self.assertEqual(Flag.objects.filter(realm_id="realm-a").count(), 1)
        self.assertEqual(Flag.objects.filter(realm_id="realm-b").count(), 0)

    def test_anomaly_detection_deletes_only_target_realm_anomaly_flags(self) -> None:
        txn_a = _make_txn(realm_id="realm-a", qb_transaction_id="QB-A")
        Flag.objects.create(
            realm_id="realm-a",
            flag_type=FlagType.ANOMALY,
            transaction=txn_a,
            reason="stale",
            severity=Severity.LOW,
        )
        txn_b = _make_txn(realm_id="realm-b", qb_transaction_id="QB-B")
        Flag.objects.create(
            realm_id="realm-b",
            flag_type=FlagType.ANOMALY,
            transaction=txn_b,
            reason="stale",
            severity=Severity.LOW,
        )

        run_anomaly_detection("2025-01", realm_id="realm-a")

        # The stale realm-a flag is replaced by a fresh new-vendor anomaly flag.
        self.assertEqual(Flag.objects.filter(realm_id="realm-a").count(), 1)
        self.assertTrue(Flag.objects.filter(realm_id="realm-b").exists())


class RealmIsolationBankFeedTests(TestCase):
    def test_generate_bank_feed_only_creates_for_target_realm(self) -> None:
        _make_txn(realm_id="realm-a", qb_transaction_id="QB-A")
        _make_txn(realm_id="realm-b", qb_transaction_id="QB-B")

        result = generate_bank_feed("2025-01", realm_id="realm-a", force=True, seed=1)

        self.assertGreater(result["created"], 0)
        self.assertEqual(BankTransaction.objects.filter(realm_id="realm-a").count(), result["created"])
        self.assertEqual(BankTransaction.objects.filter(realm_id="realm-b").count(), 0)


class RealmIsolationCloseSummaryTests(TestCase):
    def test_gather_inputs_only_includes_target_realm(self) -> None:
        _make_txn(realm_id="realm-a", qb_transaction_id="QB-A", amount=Decimal("300.00"), category="Software")
        _make_txn(realm_id="realm-b", qb_transaction_id="QB-B", amount=Decimal("700.00"), category="Software")

        inputs = gather_inputs("2025-01", realm_id="realm-a")

        self.assertEqual(inputs["total_spend"], Decimal("300.00"))
        self.assertEqual(inputs["category_totals"], {"Software": Decimal("300.00")})

    def test_draft_summary_only_creates_for_target_realm(self) -> None:
        _make_txn(realm_id="realm-a", qb_transaction_id="QB-A", amount=Decimal("300.00"), category="Software")
        _make_txn(realm_id="realm-b", qb_transaction_id="QB-B", amount=Decimal("700.00"), category="Software")

        with _config_patch():
            summary = draft_close_summary("2025-01", realm_id="realm-a")

        self.assertEqual(summary.realm_id, "realm-a")
        self.assertIn("Software", summary.summary_text)
        self.assertEqual(CloseSummary.objects.filter(realm_id="realm-a").count(), 1)
        self.assertEqual(CloseSummary.objects.filter(realm_id="realm-b").count(), 0)


class RealmIsolationQBAccountTests(TestCase):
    def test_sync_accounts_scopes_by_realm(self) -> None:
        QBAccount.objects.create(realm_id="realm-a", account_id="acc-1", name="Checking")
        QBAccount.objects.create(realm_id="realm-b", account_id="acc-1", name="Savings")

        self.assertEqual(
            QBAccount.objects.filter(realm_id="realm-a", account_id="acc-1").count(), 1
        )
        realm_a_account = QBAccount.objects.get(realm_id="realm-a", account_id="acc-1")
        self.assertEqual(realm_a_account.name, "Checking")
        realm_b_account = QBAccount.objects.get(realm_id="realm-b", account_id="acc-1")
        self.assertEqual(realm_b_account.name, "Savings")

    @mock.patch.object(qb_client.Account, "all")
    def test_sync_accounts_only_updates_target_realm(self, mock_all) -> None:
        QBAccount.objects.create(realm_id="realm-a", account_id="acc-1", name="Old")
        QBAccount.objects.create(realm_id="realm-b", account_id="acc-1", name="Untouched")

        mock_all.return_value = [
            SimpleNamespace(
                Id="acc-1", Name="Checking", AccountType="Bank",
                AccountSubType="Checking", Active=True,
            )
        ]
        qb_client.sync_accounts(mock.MagicMock(), realm_id="realm-a")

        realm_a = QBAccount.objects.get(realm_id="realm-a", account_id="acc-1")
        realm_b = QBAccount.objects.get(realm_id="realm-b", account_id="acc-1")
        self.assertEqual(realm_a.name, "Checking")
        self.assertEqual(realm_b.name, "Untouched")


class RealmIsolationDashboardViewTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="test")
        self.client = Client()
        self.client.force_login(self.user)

    def test_dashboard_defaults_to_most_recently_connected_realm(self) -> None:
        QuickBooksCompany.objects.create(realm_id="realm-a", is_connected=True)
        QuickBooksCompany.objects.create(realm_id="realm-b", is_connected=True)
        QBToken.objects.create(
            realm_id="realm-b",
            access_token_encrypted="at",
            refresh_token_encrypted="rt",
        )

        resp = self.client.get("/dashboard/")

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, 'value="realm-b"')

    def test_dashboard_company_selector_lists_all_companies(self) -> None:
        QuickBooksCompany.objects.create(realm_id="realm-a", is_connected=True)
        QuickBooksCompany.objects.create(realm_id="realm-b", is_connected=True)

        resp = self.client.get("/dashboard/")

        self.assertContains(resp, "realm-a")
        self.assertContains(resp, "realm-b")

    def test_reconcile_action_passes_realm_id_from_post(self) -> None:
        _make_txn(realm_id="realm-a", qb_transaction_id="QB-A")
        _make_bank_txn(realm_id="realm-a", qb_transaction_id="QB-A", amount=Decimal("105.00"))

        resp = self.client.post(
            "/dashboard/reconcile/",
            {"month": "2025-01", "realm_id": "realm-a"},
        )

        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Reconciliation complete")
        # One reconciliation flag + one new-vendor anomaly flag for this realm.
        self.assertEqual(Flag.objects.filter(realm_id="realm-a").count(), 2)


class RealmIsolationSyncCommandTests(TestCase):
    def _purchase(self, qbid: str) -> SimpleNamespace:
        return SimpleNamespace(
            Id=qbid,
            TxnDate="2025-01-15",
            TotalAmt="100.00",
            EntityRef=SimpleNamespace(name="Vendor Co", value=""),
            AccountRef=SimpleNamespace(name="Checking", value=""),
            qbo_object_name="Purchase",
        )

    def test_sync_all_companies_when_no_realm_id_given(self) -> None:
        token_a = mock.MagicMock(realm_id="realm-a")
        token_b = mock.MagicMock(realm_id="realm-b")
        raw = {
            "Purchase": [self._purchase("QB-A")],
            "Deposit": [],
            "JournalEntry": [],
        }
        out = StringIO()
        with mock.patch.object(qb_tokens, "get_active_tokens", return_value=[token_a, token_b]), \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", return_value=""), \
             mock.patch.object(qb_client, "pull_raw_records", return_value=raw), \
             mock.patch.object(qb_client, "sync_accounts", return_value={"created": 0, "updated": 0, "errors": 0}):
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", stdout=out)

        self.assertEqual(Transaction.objects.filter(realm_id="realm-a").count(), 1)
        self.assertEqual(Transaction.objects.filter(realm_id="realm-b").count(), 1)

    def test_sync_single_company_when_realm_id_given(self) -> None:
        token_a = mock.MagicMock(realm_id="realm-a")
        token_b = mock.MagicMock(realm_id="realm-b")
        raw = {
            "Purchase": [self._purchase("QB-A")],
            "Deposit": [],
            "JournalEntry": [],
        }
        with mock.patch.object(qb_tokens, "get_active_token", return_value=token_a), \
             mock.patch.object(qb_tokens, "get_active_tokens", return_value=[token_a, token_b]), \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", return_value=""), \
             mock.patch.object(qb_client, "pull_raw_records", return_value=raw), \
             mock.patch.object(qb_client, "sync_accounts", return_value={"created": 0, "updated": 0, "errors": 0}):
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", "--realm-id", "realm-a", stdout=StringIO())

        self.assertEqual(Transaction.objects.filter(realm_id="realm-a").count(), 1)
        self.assertEqual(Transaction.objects.filter(realm_id="realm-b").count(), 0)
