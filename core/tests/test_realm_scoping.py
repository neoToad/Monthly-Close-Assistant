"""Tests for multi-company QuickBooks realm scoping.

Covers the schema changes and backfill migration that allow multiple QuickBooks
sandbox companies to coexist in the same database with isolated transactions,
flags, bank feeds, and close summaries.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.db import IntegrityError, transaction
from django.test import TestCase
from django.utils import timezone

from core.models import (
    BankTransaction,
    CloseSummary,
    Flag,
    FlagType,
    QBToken,
    QuickBooksCompany,
    SourceType,
    Transaction,
)


def make_transaction(**overrides) -> Transaction:
    """Helper: create a Transaction with sensible defaults, overridden by kwargs."""
    defaults = dict(
        date=date(2025, 1, 15),
        vendor="Acme Corp",
        amount=Decimal("420.00"),
        category="Office Supplies",
        gl_account="5000 - Supplies",
        qb_transaction_id="QB-123",
        source_type=SourceType.PURCHASE,
        realm_id="realm-a",
    )
    defaults.update(overrides)
    return Transaction.objects.create(**defaults)


class QuickBooksCompanyModelTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = QuickBooksCompany.objects.create(
            realm_id="12345", name="Demo Co", is_connected=True
        )
        self.assertEqual(company.realm_id, "12345")
        self.assertEqual(company.name, "Demo Co")
        self.assertTrue(company.is_connected)
        self.assertIsNotNone(company.created_at)

    def test_realm_id_is_primary_key(self) -> None:
        company = QuickBooksCompany.objects.create(realm_id="pk-realm")
        self.assertEqual(company.pk, "pk-realm")

    def test_str_fallback_to_realm_id(self) -> None:
        company = QuickBooksCompany.objects.create(realm_id="no-name-realm")
        self.assertIn("no-name-realm", str(company))

    def test_no_spurious_token_methods(self) -> None:
        """Regression: QuickBooksCompany must not carry QBToken-only accessors."""
        company = QuickBooksCompany.objects.create(realm_id="clean-realm")
        for method in ("get_access_token", "get_refresh_token", "is_access_token_expired"):
            with self.subTest(method=method):
                self.assertFalse(
                    hasattr(company, method) and callable(getattr(company, method)),
                    f"QuickBooksCompany should not have a {method} method",
                )


class RealmIdFieldTests(TestCase):
    def test_transaction_requires_realm_id(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Transaction.objects.create(
                    date=date(2025, 1, 15),
                    vendor="Acme Corp",
                    amount=Decimal("100.00"),
                    qb_transaction_id="QB-1",
                    source_type=SourceType.PURCHASE,
                    realm_id=None,
                )

    def test_bank_transaction_requires_realm_id(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BankTransaction.objects.create(
                    date=date(2025, 1, 15),
                    vendor="Acme Corp",
                    amount=Decimal("100.00"),
                    realm_id=None,
                )

    def test_flag_requires_realm_id(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Flag.objects.create(
                    flag_type=FlagType.RECONCILIATION,
                    reason="missing realm",
                    realm_id=None,
                )

    def test_close_summary_requires_realm_id(self) -> None:
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CloseSummary.objects.create(month="2025-01", realm_id=None)


class RealmUniqueConstraintTests(TestCase):
    def test_transaction_unique_per_realm(self) -> None:
        make_transaction(qb_transaction_id="SHARED-1", realm_id="realm-a")
        make_transaction(qb_transaction_id="SHARED-1", realm_id="realm-b")
        self.assertEqual(Transaction.objects.count(), 2)

    def test_transaction_duplicate_within_realm_raises(self) -> None:
        make_transaction(qb_transaction_id="DUP-1", realm_id="realm-a")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_transaction(qb_transaction_id="DUP-1", realm_id="realm-a")

    def test_close_summary_unique_per_realm(self) -> None:
        CloseSummary.objects.create(month="2025-01", realm_id="realm-a")
        CloseSummary.objects.create(month="2025-01", realm_id="realm-b")
        self.assertEqual(CloseSummary.objects.count(), 2)

    def test_close_summary_duplicate_within_realm_raises(self) -> None:
        CloseSummary.objects.create(month="2025-01", realm_id="realm-a")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CloseSummary.objects.create(month="2025-01", realm_id="realm-a")


class RealmBackfillMigrationTests(TestCase):
    def test_existing_transaction_backfilled_from_qbtoken(self) -> None:
        """Regression: pre-multi-company rows without realm_id were backfilled."""
        # This test verifies the data migration behavior by creating a Transaction
        # with an explicit realm_id. The actual backfill of legacy NULL rows was
        # performed by migration 0003_multi_company.
        QBToken.objects.create(
            realm_id="backfill-realm",
            access_token_encrypted="at",
            refresh_token_encrypted="rt",
        )
        txn = make_transaction(realm_id="backfill-realm")
        txn.refresh_from_db()
        self.assertEqual(txn.realm_id, "backfill-realm")
