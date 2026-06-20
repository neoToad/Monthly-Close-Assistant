"""Tests for the ConnectWise integration models (Step 1).

Covers QBO customer/invoice models, ConnectWise master data, client mappings,
work-role burden rates, and ConnectWise activity entries.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.core.exceptions import ValidationError
from django.db import IntegrityError, transaction
from django.test import TestCase

from core.models import (
    BillingModel,
    ClientMapping,
    ConnectWiseCompany,
    ConnectWiseWorkRole,
    ExpenseEntry,
    FlagType,
    Invoice,
    InvoiceLine,
    ProductEntry,
    QBCustomer,
    QuickBooksCompany,
    Severity,
    TimeEntry,
)


def make_company(realm_id: str = "realm-a", name: str = "Demo Co") -> QuickBooksCompany:
    return QuickBooksCompany.objects.get_or_create(
        realm_id=realm_id, defaults={"name": name}
    )[0]


class QBCustomerTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        customer = QBCustomer.objects.create(
            company=company,
            realm_id="realm-a",
            customer_id="qb-cust-1",
            name="Acme Corp",
            active=True,
        )
        self.assertEqual(customer.customer_id, "qb-cust-1")
        self.assertEqual(customer.name, "Acme Corp")
        self.assertTrue(customer.active)
        self.assertEqual(customer.company, company)

    def test_unique_together_per_company(self) -> None:
        company = make_company("realm-a")
        QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="dup", name="A"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                QBCustomer.objects.create(
                    company=company, realm_id="realm-a", customer_id="dup", name="B"
                )

    def test_same_customer_id_allowed_in_different_realms(self) -> None:
        company_a = make_company("realm-a")
        company_b = make_company("realm-b")
        QBCustomer.objects.create(
            company=company_a, realm_id="realm-a", customer_id="shared", name="A"
        )
        QBCustomer.objects.create(
            company=company_b, realm_id="realm-b", customer_id="shared", name="B"
        )
        self.assertEqual(QBCustomer.objects.count(), 2)

    def test_str_representation(self) -> None:
        customer = QBCustomer.objects.create(
            company=make_company("realm-a"),
            realm_id="realm-a",
            customer_id="qb-cust-1",
            name="Acme Corp",
        )
        self.assertIn("Acme Corp", str(customer))


class ConnectWiseCompanyTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        cw_company = ConnectWiseCompany.objects.create(
            company=company,
            realm_id="realm-a",
            connectwise_id="cw-1",
            name="Acme CW",
        )
        self.assertEqual(cw_company.connectwise_id, "cw-1")
        self.assertEqual(cw_company.name, "Acme CW")

    def test_unique_together_per_company(self) -> None:
        company = make_company("realm-a")
        ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="dup", name="A"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConnectWiseCompany.objects.create(
                    company=company, realm_id="realm-a", connectwise_id="dup", name="B"
                )

    def test_str_representation(self) -> None:
        cw_company = ConnectWiseCompany.objects.create(
            company=make_company("realm-a"),
            realm_id="realm-a",
            connectwise_id="cw-1",
            name="Acme CW",
        )
        self.assertIn("Acme CW", str(cw_company))


class ClientMappingTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        qbo_customer = QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="qb-cust-1", name="Acme"
        )
        cw_company = ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="cw-1", name="Acme CW"
        )
        mapping = ClientMapping.objects.create(
            company=company,
            realm_id="realm-a",
            connectwise_company=cw_company,
            qbo_customer=qbo_customer,
            billing_model=BillingModel.HOURLY,
        )
        self.assertEqual(mapping.billing_model, BillingModel.HOURLY)
        self.assertEqual(mapping.connectwise_company, cw_company)
        self.assertEqual(mapping.qbo_customer, qbo_customer)

    def test_flat_fee_requires_flat_fee_amount(self) -> None:
        company = make_company("realm-a")
        qbo_customer = QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="qb-cust-1", name="Acme"
        )
        cw_company = ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="cw-1", name="Acme CW"
        )
        mapping = ClientMapping(
            company=company,
            realm_id="realm-a",
            connectwise_company=cw_company,
            qbo_customer=qbo_customer,
            billing_model=BillingModel.FLAT_FEE,
        )
        with self.assertRaises(ValidationError):
            mapping.full_clean()

    def test_unique_together_per_connectwise_company(self) -> None:
        company = make_company("realm-a")
        qbo_customer = QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="qb-cust-1", name="Acme"
        )
        cw_company = ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="cw-1", name="Acme CW"
        )
        ClientMapping.objects.create(
            company=company,
            realm_id="realm-a",
            connectwise_company=cw_company,
            qbo_customer=qbo_customer,
            billing_model=BillingModel.HOURLY,
        )
        second_customer = QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="qb-cust-2", name="Beta"
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClientMapping.objects.create(
                    company=company,
                    realm_id="realm-a",
                    connectwise_company=cw_company,
                    qbo_customer=second_customer,
                    billing_model=BillingModel.HOURLY,
                )

    def test_unique_together_per_qbo_customer(self) -> None:
        company = make_company("realm-a")
        qbo_customer = QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="qb-cust-1", name="Acme"
        )
        cw_company = ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="cw-1", name="Acme CW"
        )
        second_cw = ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="cw-2", name="Beta CW"
        )
        ClientMapping.objects.create(
            company=company,
            realm_id="realm-a",
            connectwise_company=cw_company,
            qbo_customer=qbo_customer,
            billing_model=BillingModel.HOURLY,
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ClientMapping.objects.create(
                    company=company,
                    realm_id="realm-a",
                    connectwise_company=second_cw,
                    qbo_customer=qbo_customer,
                    billing_model=BillingModel.HOURLY,
                )


class ConnectWiseWorkRoleTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        role = ConnectWiseWorkRole.objects.create(
            company=company,
            realm_id="realm-a",
            role_name="Senior Technician",
            burden_rate=Decimal("75.00"),
        )
        self.assertEqual(role.role_name, "Senior Technician")
        self.assertEqual(role.burden_rate, Decimal("75.00"))

    def test_unique_together_per_company(self) -> None:
        company = make_company("realm-a")
        ConnectWiseWorkRole.objects.create(
            company=company, realm_id="realm-a", role_name="Tech", burden_rate=Decimal("50.00")
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                ConnectWiseWorkRole.objects.create(
                    company=company,
                    realm_id="realm-a",
                    role_name="Tech",
                    burden_rate=Decimal("60.00"),
                )


class InvoiceTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        customer = QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="qb-cust-1", name="Acme"
        )
        invoice = Invoice.objects.create(
            company=company,
            realm_id="realm-a",
            qb_invoice_id="inv-1",
            customer=customer,
            customer_name="Acme",
            invoice_date=dt.date(2025, 1, 15),
            total_amount=Decimal("5000.00"),
        )
        self.assertEqual(invoice.qb_invoice_id, "inv-1")
        self.assertEqual(invoice.total_amount, Decimal("5000.00"))
        self.assertEqual(invoice.customer, customer)

    def test_unique_together_per_company(self) -> None:
        company = make_company("realm-a")
        customer = QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="qb-cust-1", name="Acme"
        )
        Invoice.objects.create(
            company=company,
            realm_id="realm-a",
            qb_invoice_id="dup",
            customer=customer,
            customer_name="Acme",
            invoice_date=dt.date(2025, 1, 15),
            total_amount=Decimal("100.00"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                Invoice.objects.create(
                    company=company,
                    realm_id="realm-a",
                    qb_invoice_id="dup",
                    customer=customer,
                    customer_name="Acme",
                    invoice_date=dt.date(2025, 1, 16),
                    total_amount=Decimal("200.00"),
                )


class InvoiceLineTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        customer = QBCustomer.objects.create(
            company=company, realm_id="realm-a", customer_id="qb-cust-1", name="Acme"
        )
        invoice = Invoice.objects.create(
            company=company,
            realm_id="realm-a",
            qb_invoice_id="inv-1",
            customer=customer,
            customer_name="Acme",
            invoice_date=dt.date(2025, 1, 15),
            total_amount=Decimal("5000.00"),
        )
        line = InvoiceLine.objects.create(
            company=company,
            realm_id="realm-a",
            invoice=invoice,
            line_number=1,
            description="Support services",
            amount=Decimal("5000.00"),
            service_item="Managed Services",
        )
        self.assertEqual(line.invoice, invoice)
        self.assertEqual(line.amount, Decimal("5000.00"))


class TimeEntryTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        cw_company = ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="cw-1", name="Acme CW"
        )
        entry = TimeEntry.objects.create(
            company=company,
            realm_id="realm-a",
            connectwise_entry_id="te-1",
            connectwise_company=cw_company,
            agreement_name="MSP Agreement",
            ticket_number="T-100",
            technician="Alice",
            date=dt.date(2025, 1, 15),
            hours=Decimal("2.50"),
            billable_rate=Decimal("150.00"),
            work_role="Senior Technician",
            is_billable=True,
        )
        self.assertEqual(entry.connectwise_entry_id, "te-1")
        self.assertEqual(entry.hours, Decimal("2.50"))
        self.assertTrue(entry.is_billable)

    def test_unique_together_per_company(self) -> None:
        company = make_company("realm-a")
        cw_company = ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="cw-1", name="Acme CW"
        )
        TimeEntry.objects.create(
            company=company,
            realm_id="realm-a",
            connectwise_entry_id="dup",
            connectwise_company=cw_company,
            technician="Alice",
            date=dt.date(2025, 1, 15),
            hours=Decimal("1.00"),
        )
        with self.assertRaises(IntegrityError):
            with transaction.atomic():
                TimeEntry.objects.create(
                    company=company,
                    realm_id="realm-a",
                    connectwise_entry_id="dup",
                    connectwise_company=cw_company,
                    technician="Bob",
                    date=dt.date(2025, 1, 16),
                    hours=Decimal("2.00"),
                )


class ExpenseEntryTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        cw_company = ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="cw-1", name="Acme CW"
        )
        entry = ExpenseEntry.objects.create(
            company=company,
            realm_id="realm-a",
            connectwise_entry_id="ex-1",
            connectwise_company=cw_company,
            agreement_name="MSP Agreement",
            date=dt.date(2025, 1, 15),
            amount=Decimal("120.00"),
            description="Travel",
        )
        self.assertEqual(entry.amount, Decimal("120.00"))
        self.assertEqual(entry.description, "Travel")


class ProductEntryTests(TestCase):
    def test_create_and_fields(self) -> None:
        company = make_company("realm-a")
        cw_company = ConnectWiseCompany.objects.create(
            company=company, realm_id="realm-a", connectwise_id="cw-1", name="Acme CW"
        )
        entry = ProductEntry.objects.create(
            company=company,
            realm_id="realm-a",
            connectwise_entry_id="pr-1",
            connectwise_company=cw_company,
            agreement_name="MSP Agreement",
            date=dt.date(2025, 1, 15),
            amount=Decimal("399.00"),
            description="Firewall",
        )
        self.assertEqual(entry.amount, Decimal("399.00"))


class FlagTypeConnectWiseTests(TestCase):
    def test_connectwise_choices_exist(self) -> None:
        choices = {choice[0] for choice in FlagType.choices}
        self.assertIn("connectwise_unbilled", choices)
        self.assertIn("connectwise_margin", choices)
        self.assertIn("connectwise_missing_mapping", choices)

    def test_connectwise_severity_rules(self) -> None:
        # The choice values themselves are labels; severity is decided by the engine.
        self.assertEqual(str(FlagType.CONNECTWISE_UNBILLED), "connectwise_unbilled")
        self.assertEqual(str(FlagType.CONNECTWISE_MARGIN), "connectwise_margin")
        self.assertEqual(str(FlagType.CONNECTWISE_MISSING_MAPPING), "connectwise_missing_mapping")
