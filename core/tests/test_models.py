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
    AccountReconciliationState,
    BankStatementBalance,
    BankTransaction,
    ClientMapping,
    CloseSummary,
    ConnectWiseCompany,
    ConnectWiseWorkRole,
    ExpenseEntry,
    Flag,
    FlagStatus,
    FlagType,
    Invoice,
    InvoiceLine,
    ProductEntry,
    QBAccount,
    QBCustomer,
    QBToken,
    QuickBooksCompany,
    ReconciliationStatus,
    Severity,
    SourceType,
    TimeEntry,
    Transaction,
)


def make_company(realm_id: str = "realm-a", name: str = "Demo Co") -> QuickBooksCompany:
    """Helper: create a QuickBooksCompany row, idempotent by realm_id."""
    return QuickBooksCompany.objects.get_or_create(
        realm_id=realm_id, defaults={"name": name}
    )[0]


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
        company=make_company("realm-a"),
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
        self.assertEqual(tx.company.realm_id, "realm-a")

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

    def test_company_cascade_delete_removes_transactions(self) -> None:
        tx = make_transaction()
        company = tx.company
        company.delete()
        self.assertFalse(Transaction.objects.filter(pk=tx.pk).exists())


class BankStatementBalanceTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        balance = BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-3621.93"),
            source=BankStatementBalance.Source.MANUAL,
            statement_date=date(2026, 6, 30),
            company=company,
        )
        self.assertEqual(balance.realm_id, "realm-a")
        self.assertEqual(balance.qb_account_id, "qb-acc-1")
        self.assertEqual(balance.account_name, "Operating Checking")
        self.assertEqual(balance.month, "2026-06")
        self.assertEqual(balance.ending_balance, Decimal("-3621.93"))
        self.assertEqual(balance.source, "manual")
        self.assertEqual(balance.statement_date, date(2026, 6, 30))
        self.assertEqual(balance.company, company)

    def test_unique_together_per_realm_account_month(self) -> None:
        company = make_company("realm-a")
        BankStatementBalance.objects.create(
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            account_name="Operating Checking",
            month="2026-06",
            ending_balance=Decimal("-3621.93"),
            company=company,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                BankStatementBalance.objects.create(
                    realm_id="realm-a",
                    qb_account_id="qb-acc-1",
                    account_name="Operating Checking",
                    month="2026-06",
                    ending_balance=Decimal("-3500.00"),
                    company=company,
                )

    def test_same_account_allowed_in_different_realms_or_months(self) -> None:
        company_a = make_company("realm-a")
        company_b = make_company("realm-b")
        BankStatementBalance.objects.create(
            realm_id="realm-a", qb_account_id="qb-acc-1", account_name="Checking",
            month="2026-06", ending_balance=Decimal("-100.00"), company=company_a,
        )
        BankStatementBalance.objects.create(
            realm_id="realm-b", qb_account_id="qb-acc-1", account_name="Checking",
            month="2026-06", ending_balance=Decimal("-200.00"), company=company_b,
        )
        BankStatementBalance.objects.create(
            realm_id="realm-a", qb_account_id="qb-acc-1", account_name="Checking",
            month="2026-07", ending_balance=Decimal("-300.00"), company=company_a,
        )
        self.assertEqual(BankStatementBalance.objects.count(), 3)

    def test_str_representation(self) -> None:
        balance = BankStatementBalance.objects.create(
            realm_id="realm-a", qb_account_id="qb-acc-1", account_name="Checking",
            month="2026-06", ending_balance=Decimal("-3621.93"),
            company=make_company("realm-a"),
        )
        self.assertIn("Checking", str(balance))
        self.assertIn("2026-06", str(balance))


class QBAccountTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        account = QBAccount.objects.create(
            realm_id="realm-a",
            account_id="qb-acc-1",
            name="Checking",
            account_type="Bank",
            account_sub_type="Checking",
            active=True,
            company=company,
        )
        self.assertEqual(account.realm_id, "realm-a")
        self.assertEqual(account.account_id, "qb-acc-1")
        self.assertEqual(account.name, "Checking")
        self.assertEqual(account.account_type, "Bank")
        self.assertEqual(account.account_sub_type, "Checking")
        self.assertTrue(account.active)
        self.assertEqual(account.company, company)

    def test_unique_together_per_realm(self) -> None:
        company = make_company("realm-a")
        QBAccount.objects.create(realm_id="realm-a", account_id="dup", name="A", company=company)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                QBAccount.objects.create(realm_id="realm-a", account_id="dup", name="B", company=company)

    def test_same_account_id_allowed_in_different_realms(self) -> None:
        company_a = make_company("realm-a")
        company_b = make_company("realm-b")
        QBAccount.objects.create(realm_id="realm-a", account_id="shared", name="A", company=company_a)
        QBAccount.objects.create(realm_id="realm-b", account_id="shared", name="B", company=company_b)
        self.assertEqual(QBAccount.objects.count(), 2)

    def test_str_representation(self) -> None:
        account = QBAccount.objects.create(
            realm_id="realm-a", account_id="qb-acc-1", name="Checking",
            company=make_company("realm-a"),
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
            company=make_company("realm-a"),
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
            company=tx.company,
        )
        self.assertEqual(bt.matched_transaction_id, tx)
        tx.delete()
        bt.refresh_from_db()
        self.assertIsNone(bt.matched_transaction_id)


class FlagTests(TestCase):
    def test_default_status_is_open(self) -> None:
        flag = Flag.objects.create(
            flag_type=FlagType.RECONCILIATION, reason="oops", realm_id="realm-a",
            company=make_company("realm-a"),
        )
        self.assertEqual(flag.status, FlagStatus.OPEN)
        self.assertEqual(flag.status, "open")

    def test_default_severity_is_low(self) -> None:
        flag = Flag.objects.create(
            flag_type=FlagType.ANOMALY, reason="weird amount", realm_id="realm-a",
            company=make_company("realm-a"),
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
            company=tx.company,
        )
        self.assertEqual(flag.transaction, tx)
        self.assertIsNone(flag.bank_transaction)
        self.assertEqual(flag.severity, Severity.HIGH)
        self.assertEqual(flag.status, FlagStatus.APPROVED)
        self.assertIn("452.00", flag.reason)
        self.assertEqual(flag.company, tx.company)

    def test_can_reference_a_bank_transaction(self) -> None:
        company = make_company("realm-a")
        bt = BankTransaction.objects.create(
            date=date(2025, 1, 15), vendor="Acme", amount=Decimal("10.00"),
            realm_id="realm-a", company=company,
        )
        flag = Flag.objects.create(
            flag_type=FlagType.ANOMALY,
            bank_transaction=bt,
            reason="duplicate",
            realm_id=bt.realm_id,
            company=company,
        )
        self.assertEqual(flag.bank_transaction, bt)
        self.assertIsNone(flag.transaction)

    def test_created_at_is_set(self) -> None:
        flag = Flag.objects.create(
            flag_type=FlagType.RECONCILIATION, reason="x", realm_id="realm-a",
            company=make_company("realm-a"),
        )
        self.assertIsNotNone(flag.created_at)


class CloseSummaryTests(TestCase):
    def test_defaults_are_draft(self) -> None:
        summary = CloseSummary.objects.create(
            month="2025-01", realm_id="realm-a", company=make_company("realm-a")
        )
        self.assertEqual(summary.status, "draft")
        self.assertEqual(summary.summary_text, "")
        self.assertEqual(summary.reviewer_notes, "")

    def test_month_unique_per_realm(self) -> None:
        CloseSummary.objects.create(month="2025-02", realm_id="realm-a", company=make_company("realm-a"))
        CloseSummary.objects.create(month="2025-02", realm_id="realm-b", company=make_company("realm-b"))
        self.assertEqual(CloseSummary.objects.count(), 2)
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                CloseSummary.objects.create(
                    month="2025-02", realm_id="realm-a", company=make_company("realm-a")
                )

    def test_reviewed_flow(self) -> None:
        summary = CloseSummary.objects.create(
            month="2025-03",
            summary_text="Spend rose 12% driven by software.",
            status="reviewed",
            reviewer_notes="Looks good — approved.",
            realm_id="realm-a",
            company=make_company("realm-a"),
        )
        self.assertEqual(summary.status, "reviewed")
        self.assertIn("software", summary.summary_text)
        self.assertIn("approved", summary.reviewer_notes)

    def test_created_at_is_set(self) -> None:
        summary = CloseSummary.objects.create(
            month="2025-04", realm_id="realm-a", company=make_company("realm-a")
        )
        self.assertIsNotNone(summary.created_at)


class QBTokenCompanyTests(TestCase):
    def test_token_links_to_company(self) -> None:
        company = make_company("realm-a")
        token = QBToken.objects.create(
            realm_id="realm-a",
            access_token_encrypted="at",
            refresh_token_encrypted="rt",
            company=company,
        )
        self.assertEqual(token.company, company)


class AccountReconciliationStateTests(TestCase):
    def test_defaults_unreconciled(self) -> None:
        company = make_company("realm-a")
        state = AccountReconciliationState.objects.create(
            company=company,
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            month="2026-06",
            statement_balance=Decimal("-3621.93"),
        )
        self.assertEqual(state.status, ReconciliationStatus.UNRECONCILED)
        self.assertEqual(state.status, "unreconciled")
        self.assertEqual(state.posted_total, Decimal("0.00"))
        self.assertEqual(state.difference, Decimal("0.00"))

    def test_unique_together_per_company_account_month(self) -> None:
        company = make_company("realm-a")
        AccountReconciliationState.objects.create(
            company=company,
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            month="2026-06",
            statement_balance=Decimal("-3621.93"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                AccountReconciliationState.objects.create(
                    company=company,
                    realm_id="realm-a",
                    qb_account_id="qb-acc-1",
                    month="2026-06",
                    statement_balance=Decimal("-3500.00"),
                )

    def test_same_account_in_different_months(self) -> None:
        company = make_company("realm-a")
        AccountReconciliationState.objects.create(
            company=company, realm_id="realm-a", qb_account_id="qb-acc-1",
            month="2026-06", statement_balance=Decimal("-100.00"),
        )
        AccountReconciliationState.objects.create(
            company=company, realm_id="realm-a", qb_account_id="qb-acc-1",
            month="2026-07", statement_balance=Decimal("-200.00"),
        )
        self.assertEqual(AccountReconciliationState.objects.count(), 2)


class FlagNotesTests(TestCase):
    def test_notes_field_defaults_blank(self) -> None:
        flag = Flag.objects.create(
            flag_type=FlagType.RECONCILIATION,
            reason="mismatch",
            realm_id="realm-a",
            company=make_company("realm-a"),
        )
        self.assertEqual(flag.notes, "")

    def test_notes_field_stores_audit_text(self) -> None:
        flag = Flag.objects.create(
            flag_type=FlagType.BALANCE_RECONCILIATION,
            reason="gap",
            notes="Created JE-123 for $53.55",
            realm_id="realm-a",
            company=make_company("realm-a"),
        )
        self.assertIn("JE-123", flag.notes)


class AdminRegistrationTests(TestCase):
    def test_all_models_registered_in_admin(self) -> None:
        for model in (
            AccountReconciliationState,
            BankStatementBalance,
            Transaction,
            BankTransaction,
            Flag,
            CloseSummary,
            QBAccount,
            QBToken,
            QuickBooksCompany,
            QBCustomer,
            ConnectWiseCompany,
            ClientMapping,
            ConnectWiseWorkRole,
            Invoice,
            InvoiceLine,
            TimeEntry,
            ExpenseEntry,
            ProductEntry,
        ):
            self.assertIn(
                model,
                admin.site._registry,
                f"{model.__name__} is not registered in admin.site",
            )
