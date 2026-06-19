"""Tests for the QuickBooks integration service (Prompt 3 — QuickBooks OAuth + Pull).

Covers the pure, mockable boundaries of the sync pipeline:

* token encryption-at-rest helpers (roundtrip + plaintext dev fallback).
* ``normalize_record`` turning QuickBooks Purchase / Deposit / JournalEntry objects
  into the internal ``Transaction`` field dict (and skipping records without an id/date).
* ``sync_transactions`` orchestrating pull → normalize → ``get_or_create`` (idempotent
  skip-existing by ``qb_transaction_id``) and reporting counts.
* ``refresh_tokens`` driving an ``AuthClient`` refresh and returning the new tokens.

No live QuickBooks sandbox is contacted: ``pull_raw_records`` is patched everywhere.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.test import SimpleTestCase, TestCase, override_settings
from django.utils import timezone

from core.quickbooks import client as qb_client
from core.quickbooks.tokens import decrypt_value, encrypt_value, store_tokens


def _ref(name: str = "", value: str = "") -> SimpleNamespace:
    """A stand-in for the python-quickbooks ``Ref`` object (has .name/.value)."""
    return SimpleNamespace(name=name, value=value)


def _purchase(*, id_: str = "1", date: str = "2026-05-10", amount="123.45",
              vendor="Acme Supplies", account="Checking") -> SimpleNamespace:
    return SimpleNamespace(
        Id=id_,
        TxnDate=date,
        TotalAmt=amount,
        EntityRef=_ref(name=vendor),
        AccountRef=_ref(name=account),
        qbo_object_name="Purchase",
    )


def _deposit(*, id_: str = "2", date: str = "2026-05-11", amount="500.00",
             account="Operating Bank") -> SimpleNamespace:
    return SimpleNamespace(
        Id=id_,
        TxnDate=date,
        TotalAmt=amount,
        DepositToAccountRef=_ref(name=account),
        qbo_object_name="Deposit",
    )


def _journal_entry(*, id_: str = "3", date: str = "2026-05-12", amount="75.00",
                   debit_account="Depreciation Expense") -> SimpleNamespace:
    line = SimpleNamespace(
        Amount=amount,
        PostingType="Debit",
        JournalEntryLineDetail=SimpleNamespace(AccountRef=_ref(name=debit_account)),
    )
    return SimpleNamespace(
        Id=id_,
        TxnDate=date,
        TotalAmt=amount,
        Line=[line],
        qbo_object_name="JournalEntry",
    )


# ---------------------------------------------------------------------------
# Token encryption at rest
# ---------------------------------------------------------------------------


class TokenEncryptionTests(SimpleTestCase):
    """Fernet-backed encryption with a plaintext dev fallback when no key is set."""

    def test_plaintext_passthrough_when_no_key(self) -> None:
        # With no encryption key configured, values pass through unchanged so
        # local development works without provisioning a Fernet key.
        with override_settings(QB_TOKEN_ENCRYPTION_KEY=""):
            self.assertEqual(encrypt_value("abc"), "abc")
            self.assertEqual(decrypt_value("abc"), "abc")

    def test_roundtrip_with_key(self) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        with override_settings(QB_TOKEN_ENCRYPTION_KEY=key):
            ciphertext = encrypt_value("a-secret-token")
            self.assertNotEqual(ciphertext, "a-secret-token")
            self.assertEqual(decrypt_value(ciphertext), "a-secret-token")

    def test_ciphertext_differs_for_different_plaintexts(self) -> None:
        from cryptography.fernet import Fernet

        key = Fernet.generate_key().decode()
        with override_settings(QB_TOKEN_ENCRYPTION_KEY=key):
            self.assertNotEqual(encrypt_value("one"), encrypt_value("two"))


class StoreTokensTests(TestCase):
    def test_stores_tokens_and_creates_quickbooks_company(self) -> None:
        from core.models import QBToken, QuickBooksCompany

        auth_client = SimpleNamespace(
            access_token="at",
            refresh_token="rt",
            expires_in=3600,
            x_refresh_token_expires_in=8700000,
            realm_id="12345",
        )
        token = store_tokens(auth_client, realm_id="12345")

        self.assertEqual(token.realm_id, "12345")
        self.assertEqual(token.get_access_token(), "at")
        self.assertTrue(
            QuickBooksCompany.objects.filter(realm_id="12345").exists()
        )
        company = QuickBooksCompany.objects.get(realm_id="12345")
        self.assertTrue(company.is_connected)

    def test_store_tokens_sets_company_name_when_provided(self) -> None:
        from core.models import QuickBooksCompany

        auth_client = SimpleNamespace(
            access_token="at",
            refresh_token="rt",
            expires_in=3600,
            x_refresh_token_expires_in=8700000,
            realm_id="12345",
        )
        store_tokens(auth_client, realm_id="12345", company_name="Demo Co")

        company = QuickBooksCompany.objects.get(realm_id="12345")
        self.assertEqual(company.name, "Demo Co")

    def test_store_tokens_preserves_existing_name_when_not_provided(self) -> None:
        from core.models import QuickBooksCompany

        QuickBooksCompany.objects.create(realm_id="12345", name="Existing Name")
        auth_client = SimpleNamespace(
            access_token="at",
            refresh_token="rt",
            expires_in=3600,
            x_refresh_token_expires_in=8700000,
            realm_id="12345",
        )
        store_tokens(auth_client, realm_id="12345")

        company = QuickBooksCompany.objects.get(realm_id="12345")
        self.assertEqual(company.name, "Existing Name")


# ---------------------------------------------------------------------------
# normalize_record
# ---------------------------------------------------------------------------


class NormalizeRecordTests(SimpleTestCase):
    def test_purchase_maps_vendor_amount_and_gl_account(self) -> None:
        norm = qb_client.normalize_record(_purchase(), "Purchase")
        self.assertEqual(norm["qb_transaction_id"], "1")
        self.assertEqual(norm["date"], dt.date(2026, 5, 10))
        self.assertEqual(norm["amount"], Decimal("123.45"))
        self.assertEqual(norm["vendor"], "Acme Supplies")
        self.assertEqual(norm["gl_account"], "Checking")
        self.assertEqual(norm["source_type"], "Purchase")

    def test_deposit_uses_deposit_account_as_gl(self) -> None:
        norm = qb_client.normalize_record(_deposit(), "Deposit")
        self.assertEqual(norm["qb_transaction_id"], "2")
        self.assertEqual(norm["vendor"], "Deposit")
        self.assertEqual(norm["gl_account"], "Operating Bank")
        self.assertEqual(norm["source_type"], "Deposit")

    def test_journal_entry_sums_debit_and_uses_first_debit_account(self) -> None:
        norm = qb_client.normalize_record(_journal_entry(), "JournalEntry")
        self.assertEqual(norm["qb_transaction_id"], "3")
        self.assertEqual(norm["vendor"], "Journal Entry")
        self.assertEqual(norm["gl_account"], "Depreciation Expense")
        self.assertEqual(norm["amount"], Decimal("75.00"))
        self.assertEqual(norm["source_type"], "JournalEntry")

    def test_missing_id_is_skipped(self) -> None:
        self.assertIsNone(qb_client.normalize_record(_purchase(id_=""), "Purchase"))

    def test_missing_date_is_skipped(self) -> None:
        self.assertIsNone(qb_client.normalize_record(_purchase(date=""), "Purchase"))


# ---------------------------------------------------------------------------
# sync_transactions (DB-backed; pull_raw_records patched)
# ---------------------------------------------------------------------------


class SyncTransactionsTests(TestCase):
    def _raw(self) -> dict:
        return {
            "Purchase": [_purchase(), _purchase(id_="99", date="", amount="10.00")],
            "Deposit": [_deposit()],
            "JournalEntry": [_journal_entry()],
        }

    @mock.patch.object(qb_client, "pull_raw_records")
    def test_creates_new_transactions_tagged_with_realm(self, mock_pull) -> None:
        from core.models import Transaction

        mock_pull.return_value = self._raw()
        result = qb_client.sync_transactions(qb_client=object(), realm_id="realm-a")
        # 3 valid records (Purchase x1, Deposit x1, JournalEntry x1) created;
        # 1 invalid (empty date) skipped.
        self.assertEqual(result["created"], 3)
        self.assertEqual(result["skipped"], 1)
        self.assertEqual(result["per_type"]["Purchase"]["created"], 1)
        self.assertEqual(result["per_type"]["Purchase"]["skipped"], 1)
        self.assertEqual(result["per_type"]["Deposit"]["created"], 1)
        self.assertEqual(result["per_type"]["JournalEntry"]["created"], 1)
        self.assertEqual(Transaction.objects.count(), 3)
        self.assertTrue(
            Transaction.objects.filter(realm_id="realm-a").count() == 3
        )

    @mock.patch.object(qb_client, "pull_raw_records")
    def test_second_run_is_idempotent(self, mock_pull) -> None:
        from core.models import Transaction

        mock_pull.return_value = self._raw()
        qb_client.sync_transactions(qb_client=object(), realm_id="realm-a")
        second = qb_client.sync_transactions(qb_client=object(), realm_id="realm-a")
        # The 3 previously-created records are skipped; the 1 invalid record is
        # skipped again; nothing new is created. DB unchanged.
        self.assertEqual(second["created"], 0)
        self.assertEqual(second["skipped"], 4)
        self.assertEqual(Transaction.objects.count(), 3)


# ---------------------------------------------------------------------------
# pull_raw_records (regression for argument order)
# ---------------------------------------------------------------------------


class PullRawRecordsTests(SimpleTestCase):
    def test_fetch_passes_quickbooks_client_as_qb_argument(self) -> None:
        """Regression: _fetch must call model.all(qb=client), not the reverse."""
        mock_qb = mock.MagicMock()
        captured: dict = {}

        class FakeModel:
            @classmethod
            def all(cls, qb):
                captured["qb"] = qb
                return ["record-1"]

        with mock.patch.object(qb_client, "SYNC_OBJECTS", {"Fake": FakeModel}), \
             mock.patch("core.quickbooks.client.time.sleep"):
            result = qb_client.pull_raw_records(mock_qb, qb_token=None)

        self.assertEqual(result, {"Fake": ["record-1"]})
        self.assertIs(captured["qb"], mock_qb)


# ---------------------------------------------------------------------------
# refresh_tokens
# ---------------------------------------------------------------------------


class RefreshTokensTests(SimpleTestCase):
    def test_refresh_drives_auth_client_and_returns_tokens(self) -> None:
        auth_client = mock.MagicMock()
        auth_client.refresh_token = "old-refresh"
        # refresh() mutates the client in place (Intuit sets these attrs).
        def fake_refresh(refresh_token=None):
            auth_client.access_token = "new-access"
            auth_client.refresh_token = "new-refresh"
            auth_client.expires_in = 3600
            auth_client.x_refresh_token_expires_in = 8700000
        auth_client.refresh.side_effect = fake_refresh

        result = qb_client.refresh_tokens(auth_client)
        auth_client.refresh.assert_called_once()
        self.assertEqual(result["access_token"], "new-access")
        self.assertEqual(result["refresh_token"], "new-refresh")
        # expiry datetimes are in the future.
        self.assertGreater(result["access_token_expires_at"], timezone.now())
        self.assertGreater(result["refresh_token_expires_at"], timezone.now())


# ---------------------------------------------------------------------------
# environment config + API base URL (Prompt 4)
# ---------------------------------------------------------------------------


class EnvironmentConfigTests(SimpleTestCase):
    def test_environment_defaults_to_sandbox(self) -> None:
        with override_settings(QB_ENVIRONMENT=""):
            self.assertEqual(qb_client.get_environment(), "sandbox")

    def test_environment_reads_from_settings(self) -> None:
        with override_settings(QB_ENVIRONMENT="production"):
            self.assertEqual(qb_client.get_environment(), "production")

    def test_environment_is_case_normalized(self) -> None:
        with override_settings(QB_ENVIRONMENT="PRODUCTION"):
            self.assertEqual(qb_client.get_environment(), "production")

    def test_invalid_environment_raises(self) -> None:
        with override_settings(QB_ENVIRONMENT="staging"):
            with self.assertRaises(ValueError):
                qb_client.get_environment()

    def test_sandbox_api_base_url(self) -> None:
        self.assertEqual(
            qb_client.get_api_base_url("sandbox"),
            "https://sandbox-quickbooks.api.intuit.com/v3/company/",
        )

    def test_production_api_base_url(self) -> None:
        self.assertEqual(
            qb_client.get_api_base_url("production"),
            "https://quickbooks.api.intuit.com/v3/company/",
        )

    def test_make_auth_client_uses_configured_environment(self) -> None:
        with override_settings(QB_ENVIRONMENT="production"), \
             mock.patch.object(qb_client, "config") as mock_config:
            mock_config.side_effect = lambda key, default="": {
                "QB_CLIENT_ID": "id",
                "QB_CLIENT_SECRET": "secret",
                "QB_REDIRECT_URI": "http://localhost/callback/",
            }.get(key, default)
            client = qb_client.make_auth_client(realm_id="12345")
            self.assertEqual(client.environment, "production")


# ---------------------------------------------------------------------------
# token expiry with refresh buffer (Prompt 4)
# ---------------------------------------------------------------------------


class TokenExpiryBufferTests(TestCase):
    def test_not_expired_when_within_buffer(self) -> None:
        from core.models import QBToken

        token = QBToken(
            realm_id="12345",
            access_token_encrypted="at",
            refresh_token_encrypted="rt",
            access_token_expires_at=timezone.now() + dt.timedelta(minutes=10),
        )
        # With a 15-minute buffer, a token expiring in 10 minutes is considered expired.
        self.assertTrue(token.is_access_token_expired(buffer_minutes=15))

    def test_not_expired_when_beyond_buffer(self) -> None:
        from core.models import QBToken

        token = QBToken(
            realm_id="12345",
            access_token_encrypted="at",
            refresh_token_encrypted="rt",
            access_token_expires_at=timezone.now() + dt.timedelta(minutes=30),
        )
        # With a 15-minute buffer, a token expiring in 30 minutes is still valid.
        self.assertFalse(token.is_access_token_expired(buffer_minutes=15))


# ---------------------------------------------------------------------------
# retry + refresh on sync failures (Prompt 5)
# ---------------------------------------------------------------------------


class RetryAndRefreshTests(TestCase):
    def setUp(self) -> None:
        from core.models import QBToken

        self.qb_token = QBToken.objects.create(
            realm_id="12345",
            access_token_encrypted="old-access",
            refresh_token_encrypted="old-refresh",
            access_token_expires_at=timezone.now() + dt.timedelta(minutes=30),
        )

    def _mock_client(self):
        client = mock.MagicMock()
        client.auth_client = mock.MagicMock()
        return client

    @mock.patch.object(qb_client, "refresh_and_store_tokens")
    @mock.patch.object(qb_client, "build_quickbooks_client")
    def test_proactive_refresh_when_token_expired(self, mock_build, mock_refresh) -> None:
        """If the stored token is already expired, refresh before the first call."""
        from core.models import QBToken

        expired_token = QBToken(
            realm_id="12345",
            access_token_encrypted="old-access",
            refresh_token_encrypted="old-refresh",
            access_token_expires_at=timezone.now() - dt.timedelta(minutes=1),
        )
        refreshed_token = mock.MagicMock()
        refreshed_token.realm_id = "12345"
        mock_refresh.return_value = refreshed_token
        new_client = self._mock_client()
        mock_build.return_value = new_client

        calls = []

        def operation(qb):
            calls.append("op")
            return "success"

        with mock.patch("core.quickbooks.client.time.sleep"):
            result = qb_client.call_with_retry(self._mock_client(), expired_token, operation)

        self.assertEqual(result, "success")
        mock_refresh.assert_called_once_with(expired_token)
        mock_build.assert_called_once_with(refreshed_token)
        self.assertEqual(calls, ["op"])

    @mock.patch.object(qb_client, "refresh_and_store_tokens")
    def test_auth_error_mid_sync_refreshes_and_retries_once(self, mock_refresh) -> None:
        from quickbooks.exceptions import AuthorizationException

        refreshed_token = mock.MagicMock()
        refreshed_token.realm_id = "12345"
        mock_refresh.return_value = refreshed_token
        refreshed_client = self._mock_client()

        calls = []

        def operation(qb):
            calls.append("op")
            if len(calls) == 1:
                raise AuthorizationException("auth failed", error_code=401)
            return "success"

        with mock.patch.object(qb_client, "build_quickbooks_client", return_value=refreshed_client), \
             mock.patch("core.quickbooks.client.time.sleep"):
            result = qb_client.call_with_retry(self._mock_client(), self.qb_token, operation)

        self.assertEqual(result, "success")
        self.assertEqual(calls, ["op", "op"])
        mock_refresh.assert_called_once()

    @mock.patch.object(qb_client, "refresh_and_store_tokens")
    def test_auth_error_after_refresh_fails_loudly(self, mock_refresh) -> None:
        from quickbooks.exceptions import AuthorizationException

        refreshed_token = mock.MagicMock()
        refreshed_token.realm_id = "12345"
        mock_refresh.return_value = refreshed_token

        def operation(qb):
            raise AuthorizationException("auth failed", error_code=401)

        with mock.patch.object(qb_client, "build_quickbooks_client", return_value=self._mock_client()), \
             mock.patch("core.quickbooks.client.time.sleep"), \
             self.assertRaises(AuthorizationException):
            qb_client.call_with_retry(self._mock_client(), self.qb_token, operation)

        mock_refresh.assert_called_once()

    def test_transient_error_retries_with_exponential_backoff_then_fails(self) -> None:
        from quickbooks.exceptions import QuickbooksException

        sleep_calls = []

        def fake_sleep(seconds):
            sleep_calls.append(seconds)

        def operation(qb):
            raise QuickbooksException("transient", error_code=10000)

        with mock.patch("core.quickbooks.client.time.sleep", side_effect=fake_sleep), \
             self.assertRaises(QuickbooksException):
            qb_client.call_with_retry(self._mock_client(), None, operation)

        # Initial attempt + 3 retries = 4 total calls; 3 sleeps between retries.
        self.assertEqual(sleep_calls, [2, 4, 8])

    def test_transient_error_succeeds_on_retry(self) -> None:
        from quickbooks.exceptions import QuickbooksException

        calls = []

        def operation(qb):
            calls.append("op")
            if len(calls) < 2:
                raise QuickbooksException("transient", error_code=10000)
            return "success"

        with mock.patch("core.quickbooks.client.time.sleep"):
            result = qb_client.call_with_retry(self._mock_client(), None, operation)

        self.assertEqual(result, "success")
        self.assertEqual(calls, ["op", "op"])


# ---------------------------------------------------------------------------
# fetch_company_name
# ---------------------------------------------------------------------------


class FetchCompanyNameTests(SimpleTestCase):
    def _company_info(self, *, company_name: str = "", legal_name: str = "") -> SimpleNamespace:
        return SimpleNamespace(CompanyName=company_name, LegalName=legal_name)

    @mock.patch.object(qb_client, "CompanyInfo")
    def test_returns_company_name(self, mock_company_info) -> None:
        mock_company_info.get.return_value = self._company_info(company_name="Demo Co")

        result = qb_client.fetch_company_name(mock.MagicMock())

        self.assertEqual(result, "Demo Co")
        mock_company_info.get.assert_called_once_with(id=1, qb=mock.ANY)

    @mock.patch.object(qb_client, "CompanyInfo")
    def test_falls_back_to_legal_name(self, mock_company_info) -> None:
        mock_company_info.get.return_value = self._company_info(legal_name="Legal LLC")

        result = qb_client.fetch_company_name(mock.MagicMock())

        self.assertEqual(result, "Legal LLC")

    @mock.patch.object(qb_client, "CompanyInfo")
    def test_returns_empty_when_both_blank(self, mock_company_info) -> None:
        mock_company_info.get.return_value = self._company_info()

        result = qb_client.fetch_company_name(mock.MagicMock())

        self.assertEqual(result, "")

    @mock.patch.object(qb_client, "CompanyInfo")
    def test_returns_empty_and_logs_on_api_failure(self, mock_company_info) -> None:
        mock_company_info.get.side_effect = Exception("API down")

        with self.assertLogs("core.quickbooks.client", level="WARNING") as cm:
            result = qb_client.fetch_company_name(mock.MagicMock())

        self.assertEqual(result, "")
        self.assertTrue(
            any("API down" in message for message in cm.output),
            f"Expected warning to mention API error, got: {cm.output}",
        )
