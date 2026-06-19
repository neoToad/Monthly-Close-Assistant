"""Tests for the core data models (Prompt 2 — Postgres Schema).

Covers the field shapes, choices, constraints, and relationships specified for
``Transaction``, ``BankTransaction``, ``Flag``, and ``CloseSummary``, plus their
admin registration. These are ``TestCase``-based because they persist model
instances to the (Postgres) test database.
"""
from __future__ import annotations

from datetime import date
from decimal import Decimal

from django.contrib import admin
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import (
    BankTransaction,
    CloseSummary,
    Flag,
    FlagStatus,
    FlagType,
    QBAccount,
    QBToken,
    QuickBooksCompany,
    Severity,
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


class TransactionTests(TestCase):
    def test_create_and_fields(self) -> None:
        tx = make_transaction()
        self.assertEqual(tx.vendor, "Acme Corp")
        self.assertEqual(tx.amount, Decimal("420.00"))
        self.assertEqual(tx.source_type, SourceType.PURCHASE)
        self.assertEqual(tx.source_type, "Purchase")  # TextChoices str value
        self.assertEqual(tx.category, "Office Supplies")
        self.assertEqual(tx.gl_account, "5000 - Supplies")
        self.assertEqual(tx.qb_transaction_id, "QB-123")
        self.assertEqual(tx.date, date(2025, 1, 15))

    def test_str_representation(self) -> None:
        tx = make_transaction(vendor="Globex", amount=Decimal("12.50"))
        self.assertIn("Globex", str(tx))
        self.assertIn("12.50", str(tx))

    def test_qb_transaction_id_is_unique(self) -> None:
        make_transaction(qb_transaction_id="DUP-1")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                make_transaction(qb_transaction_id="DUP-1")

    def test_source_type_choices(self) -> None:
        # The QuickBooks record types the sync pulls must be valid choices.
        valid = {
            SourceType.PURCHASE,
            SourceType.DEPOSIT,
            SourceType.JOURNAL_ENTRY,
            SourceType.BILL,
            SourceType.BILL_PAYMENT,
            SourceType.VENDOR_CREDIT,
        }
        self.assertEqual(
            {choice[0] for choice in SourceType.choices},
            {c.value for c in valid},
        )


class QBAccountTests(TestCase):
    def test_create_and_fields(self) -> None:
        account = QBAccount.objects.create(
            realm_id="realm-a",
            account_id="qb-acc-1",
            name="Checking",
            account_type="Bank",
            account_sub_type="Checking",
            active=True,
        )
        self.assertEqual(account.realm_id, "realm-a")
        self.assertEqual(account.account_id, "qb-acc-1")
        self.assertEqual(account.name, "Checking")
        self.assertEqual(account.account_type, "Bank")
        self.assertEqual(account.account_sub_type, "Checking")
        self.assertTrue(account.active)

    def test_unique_together_per_realm(self) -> None:
        QBAccount.objects.create(realm_id="realm-a", account_id="dup", name="A")
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                QBAccount.objects.create(realm_id="realm-a", account_id="dup", name="B")

    def test_same_account_id_allowed_in_different_realms(self) -> None:
        QBAccount.objects.create(realm_id="realm-a", account_id="shared", name="A")
        QBAccount.objects.create(realm_id="realm-b", account_id="shared", name="B")
        self.assertEqual(QBAccount.objects.count(), 2)

    def test_str_representation(self) -> None:
        account = QBAccount.objects.create(
            realm_id="realm-a", account_id="qb-acc-1", name="Checking"
        )
        self.assertIn("Checking", str(account))


class BankTransactionTests(TestCase):
    def test_same_shape_as_transaction_plus_matched_fk(self) -> None:
        tx_fields = {f.name for f in Transaction._meta.local_fields}
        bt_fields = {f.name for f in BankTransaction._meta.local_fields}
        # Bank feed mirrors the Transaction shape...
        self.assertTrue(
            tx_fields.issubset(bt_fields),
            f"BankTransaction missing fields: {tx_fields - bt_fields}",
        )
        # ...and adds the nullable matched_transaction_id FK.
        self.assertIn("matched_transaction_id", bt_fields - tx_fields)

    def test_matched_transaction_fk_nullable(self) -> None:
        bt = BankTransaction.objects.create(
            date=date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("420.00"),
            realm_id="realm-a",
        )
        self.assertIsNone(bt.matched_transaction_id)

    def test_matched_transaction_set_null_on_delete(self) -> None:
        tx = make_transaction(qb_transaction_id="QB-MATCH")
        bt = BankTransaction.objects.create(
            date=date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("420.00"),
            matched_transaction_id=tx,
            realm_id=tx.realm_id,
        )
        self.assertEqual(bt.matched_transaction_id, tx)
        tx.delete()
        bt.refresh_from_db()
        self.assertIsNone(bt.matched_transaction_id)


class FlagTests(TestCase):
    def test_default_status_is_open(self) -> None:
        flag = Flag.objects.create(
            flag_type=FlagType.RECONCILIATION, reason="oops", realm_id="realm-a"
        )
        self.assertEqual(flag.status, FlagStatus.OPEN)
        self.assertEqual(flag.status, "open")

    def test_default_severity_is_low(self) -> None:
        flag = Flag.objects.create(
            flag_type=FlagType.ANOMALY, reason="weird amount", realm_id="realm-a"
        )
        self.assertEqual(flag.severity, Severity.LOW)

    def test_can_reference_a_transaction(self) -> None:
        tx = make_transaction()
        flag = Flag.objects.create(
            flag_type=FlagType.RECONCILIATION,
            transaction=tx,
            reason="Bank shows $452.00 but GL shows $450.00",
            severity=Severity.HIGH,
            status=FlagStatus.APPROVED,
            realm_id=tx.realm_id,
        )
        self.assertEqual(flag.transaction, tx)
        self.assertIsNone(flag.bank_transaction)
        self.assertEqual(flag.severity, Severity.HIGH)
        self.assertEqual(flag.status, FlagStatus.APPROVED)
        self.assertIn("452.00", flag.reason)

    def test_can_reference_a_bank_transaction(self) -> None:
        bt = BankTransaction.objects.create(
            date=date(2025, 1, 15), vendor="Acme", amount=Decimal("10.00"),
            realm_id="realm-a",
        )
        flag = Flag.objects.create(
            flag_type=FlagType.ANOMALY,
            bank_transaction=bt,
            reason="duplicate",
            realm_id=bt.realm_id,
        )
        self.assertEqual(flag.bank_transaction, bt)
        self.assertIsNone(flag.transaction)

    def test_created_at_is_set(self) -> None:
        flag = Flag.objects.create(
            flag_type=FlagType.RECONCILIATION, reason="x", realm_id="realm-a"
        )
        self.assertIsNotNone(flag.created_at)


class CloseSummaryTests(TestCase):
    def test_defaults_are_draft(self) -> None:
        summary = CloseSummary.objects.create(month="2025-01", realm_id="realm-a")
        self.assertEqual(summary.status, "draft")
        self.assertEqual(summary.summary_text, "")
        self.assertEqual(summary.reviewer_notes, "")

    def test_month_unique_per_realm(self) -> None:
        CloseSummary.objects.create(month="2025-02", realm_id="realm-a")
        CloseSummary.objects.create(month="2025-02", realm_id="realm-b")
        self.assertEqual(CloseSummary.objects.count(), 2)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CloseSummary.objects.create(month="2025-02", realm_id="realm-a")

    def test_reviewed_flow(self) -> None:
        summary = CloseSummary.objects.create(
            month="2025-03",
            summary_text="Spend rose 12% driven by software.",
            status="reviewed",
            reviewer_notes="Looks good — approved.",
            realm_id="realm-a",
        )
        self.assertEqual(summary.status, "reviewed")
        self.assertIn("software", summary.summary_text)
        self.assertIn("approved", summary.reviewer_notes)

    def test_created_at_is_set(self) -> None:
        summary = CloseSummary.objects.create(month="2025-04", realm_id="realm-a")
        self.assertIsNotNone(summary.created_at)


class AdminRegistrationTests(TestCase):
    def test_all_models_registered_in_admin(self) -> None:
        for model in (Transaction, BankTransaction, Flag, CloseSummary, QBAccount, QBToken, QuickBooksCompany):
            self.assertIn(
                model,
                admin.site._registry,
                f"{model.__name__} is not registered in admin.site",
            )