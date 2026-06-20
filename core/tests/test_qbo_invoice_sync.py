"""Tests for QBO customer and invoice sync (ConnectWise Step 2).

These tests exercise ``sync_customers`` and ``sync_invoices`` with mocked
python-quickbooks SDK objects so no live sandbox is contacted.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from types import SimpleNamespace
from unittest import mock

from django.core.management import call_command
from django.test import TestCase
from io import StringIO

from core.models import (
    Invoice,
    InvoiceLine,
    QBCustomer,
    QuickBooksCompany,
)
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens


def _make_customer(**overrides) -> object:
    defaults = dict(
        Id="cust-1",
        DisplayName="Acme Corp",
        FullyQualifiedName="Acme Corp",
        Active=True,
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


def _make_invoice(**overrides) -> object:
    def ref(name="", value=""):
        return SimpleNamespace(name=name, value=value)

    def line(**line_overrides):
        line_defaults = dict(
            Id="line-1",
            Description="Support services",
            Amount="5000.00",
            SalesItemLineDetail=SimpleNamespace(ItemRef=ref("Managed Services")),
        )
        line_defaults.update(line_overrides)
        return SimpleNamespace(**line_defaults)

    defaults = dict(
        Id="inv-1",
        TxnDate="2025-01-15",
        TotalAmt="5000.00",
        CustomerRef=ref("Acme Corp", "cust-1"),
        Line=[line(), line(Id="line-2", Description="Extra", Amount="250.00")],
    )
    defaults.update(overrides)
    return SimpleNamespace(**defaults)


class SyncCustomersTests(TestCase):
    def test_creates_qb_customers_from_sdk_objects(self) -> None:
        company = QuickBooksCompany.objects.for_realm("realm-a")
        customers = [
            _make_customer(Id="cust-1", DisplayName="Acme Corp"),
            _make_customer(Id="cust-2", DisplayName="Beta LLC", Active=False),
        ]

        with mock.patch.object(qb_client, "call_with_retry", return_value=customers):
            result = qb_client.sync_customers(mock.MagicMock(), realm_id="realm-a")

        self.assertEqual(result["created"], 2)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(QBCustomer.objects.count(), 2)

        acme = QBCustomer.objects.get(customer_id="cust-1")
        self.assertEqual(acme.name, "Acme Corp")
        self.assertTrue(acme.active)
        self.assertEqual(acme.company, company)

        beta = QBCustomer.objects.get(customer_id="cust-2")
        self.assertFalse(beta.active)

    def test_updates_existing_customer(self) -> None:
        company = QuickBooksCompany.objects.for_realm("realm-a")
        QBCustomer.objects.create(
            company=company,
            realm_id="realm-a",
            customer_id="cust-1",
            name="Old Name",
            active=True,
        )

        with mock.patch.object(
            qb_client, "call_with_retry", return_value=[_make_customer(Id="cust-1", DisplayName="Acme Corp")]
        ):
            result = qb_client.sync_customers(mock.MagicMock(), realm_id="realm-a")

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        acme = QBCustomer.objects.get(customer_id="cust-1")
        self.assertEqual(acme.name, "Acme Corp")

    def test_skips_customer_without_id_or_name(self) -> None:
        customers = [
            _make_customer(Id="", DisplayName="No ID"),
            _make_customer(Id="cust-2", DisplayName="", FullyQualifiedName=""),
        ]
        with mock.patch.object(qb_client, "call_with_retry", return_value=customers):
            result = qb_client.sync_customers(mock.MagicMock(), realm_id="realm-a")

        self.assertEqual(result["skipped"], 2)
        self.assertEqual(QBCustomer.objects.count(), 0)

    def test_is_idempotent_across_runs(self) -> None:
        customers = [_make_customer(Id="cust-1", DisplayName="Acme Corp")]
        with mock.patch.object(qb_client, "call_with_retry", return_value=customers):
            qb_client.sync_customers(mock.MagicMock(), realm_id="realm-a")
            result = qb_client.sync_customers(mock.MagicMock(), realm_id="realm-a")

        self.assertEqual(QBCustomer.objects.count(), 1)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)

    def test_realm_scoping(self) -> None:
        customers = [_make_customer(Id="cust-1", DisplayName="Acme Corp")]
        with mock.patch.object(qb_client, "call_with_retry", return_value=customers):
            qb_client.sync_customers(mock.MagicMock(), realm_id="realm-a")
            qb_client.sync_customers(mock.MagicMock(), realm_id="realm-b")

        self.assertEqual(QBCustomer.objects.filter(realm_id="realm-a").count(), 1)
        self.assertEqual(QBCustomer.objects.filter(realm_id="realm-b").count(), 1)


class SyncInvoicesTests(TestCase):
    def test_creates_invoices_and_lines(self) -> None:
        company = QuickBooksCompany.objects.for_realm("realm-a")
        QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="cust-1", name="Acme Corp"
        )
        invoice = _make_invoice(Id="inv-1", CustomerRef=SimpleNamespace(name="Acme Corp", value="cust-1"))

        with mock.patch.object(qb_client, "call_with_retry", return_value=[invoice]):
            result = qb_client.sync_invoices(mock.MagicMock(), realm_id="realm-a")

        self.assertEqual(result["created"], 1)
        self.assertEqual(result["updated"], 0)
        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(InvoiceLine.objects.count(), 2)

        inv = Invoice.objects.get(qb_invoice_id="inv-1")
        self.assertEqual(inv.customer_name, "Acme Corp")
        self.assertEqual(inv.total_amount, Decimal("5000.00"))
        self.assertEqual(inv.invoice_date, dt.date(2025, 1, 15))
        self.assertEqual(inv.company, company)

        lines = list(inv.lines.order_by("line_number"))
        self.assertEqual(lines[0].line_number, 1)
        self.assertEqual(lines[0].amount, Decimal("5000.00"))
        self.assertEqual(lines[0].service_item, "Managed Services")
        self.assertEqual(lines[1].line_number, 2)
        self.assertEqual(lines[1].amount, Decimal("250.00"))

    def test_updates_existing_invoice_and_replaces_lines(self) -> None:
        company = QuickBooksCompany.objects.for_realm("realm-a")
        customer = QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="cust-1", name="Acme Corp"
        )
        invoice = Invoice.objects.create(
            company=company,
            realm_id="realm-a",
            qb_invoice_id="inv-1",
            customer=customer,
            customer_name="Acme Corp",
            invoice_date=dt.date(2025, 1, 1),
            total_amount=Decimal("100.00"),
        )
        InvoiceLine.objects.create(
            company=company,
            realm_id="realm-a",
            invoice=invoice,
            line_number=1,
            amount=Decimal("100.00"),
        )

        updated = _make_invoice(
            Id="inv-1",
            CustomerRef=SimpleNamespace(name="Acme Corp", value="cust-1"),
            TotalAmt="6000.00",
            Line=[],
        )
        with mock.patch.object(qb_client, "call_with_retry", return_value=[updated]):
            result = qb_client.sync_invoices(mock.MagicMock(), realm_id="realm-a")

        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)
        inv = Invoice.objects.get(qb_invoice_id="inv-1")
        self.assertEqual(inv.total_amount, Decimal("6000.00"))
        self.assertEqual(inv.lines.count(), 0)

    def test_skips_invoice_without_id_or_date(self) -> None:
        company = QuickBooksCompany.objects.for_realm("realm-a")
        QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="cust-1", name="Acme Corp"
        )
        bad_invoices = [
            _make_invoice(Id="", CustomerRef=SimpleNamespace(name="Acme Corp", value="cust-1")),
            _make_invoice(Id="inv-bad", TxnDate="", CustomerRef=SimpleNamespace(name="Acme Corp", value="cust-1")),
        ]
        with mock.patch.object(qb_client, "call_with_retry", return_value=bad_invoices):
            result = qb_client.sync_invoices(mock.MagicMock(), realm_id="realm-a")

        self.assertEqual(result["skipped"], 2)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_invoice_without_local_customer_is_skipped(self) -> None:
        invoice = _make_invoice(
            Id="inv-1",
            CustomerRef=SimpleNamespace(name="Unknown", value="cust-unknown"),
        )
        with mock.patch.object(qb_client, "call_with_retry", return_value=[invoice]):
            result = qb_client.sync_invoices(mock.MagicMock(), realm_id="realm-a")

        self.assertEqual(result["skipped"], 1)
        self.assertEqual(Invoice.objects.count(), 0)

    def test_is_idempotent_across_runs(self) -> None:
        company = QuickBooksCompany.objects.for_realm("realm-a")
        QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="cust-1", name="Acme Corp"
        )
        invoice = _make_invoice(CustomerRef=SimpleNamespace(name="Acme Corp", value="cust-1"))
        with mock.patch.object(qb_client, "call_with_retry", return_value=[invoice]):
            qb_client.sync_invoices(mock.MagicMock(), realm_id="realm-a")
            result = qb_client.sync_invoices(mock.MagicMock(), realm_id="realm-a")

        self.assertEqual(Invoice.objects.count(), 1)
        self.assertEqual(result["created"], 0)
        self.assertEqual(result["updated"], 1)


class SyncCommandCustomerInvoiceTests(TestCase):
    def _fake_token(self, realm_id: str = "realm-a"):
        token = mock.MagicMock()
        token.realm_id = realm_id
        return token

    def test_command_calls_customer_and_invoice_sync(self) -> None:
        token = self._fake_token("realm-a")
        company = QuickBooksCompany.objects.for_realm("realm-a")
        QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="cust-1", name="Acme Corp"
        )
        out = StringIO()
        with mock.patch.object(qb_tokens, "get_active_token", return_value=token), \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", return_value=""), \
             mock.patch.object(qb_client, "sync_transactions", return_value={"created": 0, "skipped": 0, "errors": 0, "per_type": {}}), \
             mock.patch.object(qb_client, "sync_accounts", return_value={"created": 0, "updated": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_customers", return_value={"created": 1, "updated": 0, "skipped": 0, "errors": 0}) as mock_sync_customers, \
             mock.patch.object(qb_client, "sync_invoices", return_value={"created": 1, "updated": 0, "skipped": 0, "errors": 0}) as mock_sync_invoices:
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", "--realm-id", "realm-a", stdout=out)

        output = out.getvalue()
        self.assertIn("Customers: created=1", output)
        self.assertIn("Invoices: created=1", output)
        mock_sync_customers.assert_called_once()
        mock_sync_invoices.assert_called_once()

    def test_skip_customers_flag(self) -> None:
        token = self._fake_token("realm-a")
        out = StringIO()
        with mock.patch.object(qb_tokens, "get_active_token", return_value=token), \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", return_value=""), \
             mock.patch.object(qb_client, "sync_transactions", return_value={"created": 0, "skipped": 0, "errors": 0, "per_type": {}}), \
             mock.patch.object(qb_client, "sync_accounts", return_value={"created": 0, "updated": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_customers") as mock_sync_customers, \
             mock.patch.object(qb_client, "sync_invoices", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}):
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", "--realm-id", "realm-a", "--skip-customers", stdout=out)

        mock_sync_customers.assert_not_called()
        self.assertIn("Customers: skipped", out.getvalue())

    def test_skip_invoices_flag(self) -> None:
        token = self._fake_token("realm-a")
        out = StringIO()
        with mock.patch.object(qb_tokens, "get_active_token", return_value=token), \
             mock.patch.object(qb_client, "build_quickbooks_client") as mock_build, \
             mock.patch.object(qb_client, "fetch_company_name", return_value=""), \
             mock.patch.object(qb_client, "sync_transactions", return_value={"created": 0, "skipped": 0, "errors": 0, "per_type": {}}), \
             mock.patch.object(qb_client, "sync_accounts", return_value={"created": 0, "updated": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_customers", return_value={"created": 0, "updated": 0, "skipped": 0, "errors": 0}), \
             mock.patch.object(qb_client, "sync_invoices") as mock_sync_invoices:
            mock_build.return_value = mock.MagicMock()
            call_command("sync_quickbooks", "--realm-id", "realm-a", "--skip-invoices", stdout=out)

        mock_sync_invoices.assert_not_called()
        self.assertIn("Invoices: skipped", out.getvalue())
