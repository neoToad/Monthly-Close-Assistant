"""Tests for the ConnectWise-to-QBO reconciliation engine (Step 4)."""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase

from core.engines import generate_connectwise_feed, run_connectwise_reconciliation
from core.models import (
    BillingModel,
    ClientMapping,
    ConnectWiseWorkRole,
    Flag,
    FlagType,
    Invoice,
    QuickBooksCompany,
    QBCustomer,
    Severity,
)


class ConnectWiseReconciliationEngineTests(TestCase):
    """Tests for run_connectwise_reconciliation."""

    def setUp(self) -> None:
        self.month = "2025-01"
        self.realm_id = "realm-cw-reconcile"
        self.company = QuickBooksCompany.objects.for_realm(self.realm_id)

    def _create_invoice(self, customer: QBCustomer, total_amount: Decimal) -> None:
        Invoice.objects.create(
            company=self.company,
            realm_id=self.realm_id,
            qb_invoice_id=f"inv-{customer.customer_id}",
            customer=customer,
            customer_name=customer.name,
            invoice_date=dt.date(2025, 1, 15),
            total_amount=total_amount,
        )

    def test_hourly_leakage_creates_unbilled_flag(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="hourly_leakage"
        )
        customer = QBCustomer.objects.get(realm_id=self.realm_id)
        self._create_invoice(customer, Decimal("1000.00"))

        result = run_connectwise_reconciliation(month=self.month, realm_id=self.realm_id)

        self.assertEqual(result["unbilled_flags"], 1)
        flag = Flag.objects.get(realm_id=self.realm_id, flag_type=FlagType.CONNECTWISE_UNBILLED)
        self.assertIn(customer.name, flag.reason)
        self.assertIn("leakage", flag.reason.lower())
        self.assertIn(flag.severity, {Severity.HIGH, Severity.MEDIUM})

    def test_flat_fee_margin_erosion_creates_margin_flag(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="flat_fee_margin_erosion"
        )

        result = run_connectwise_reconciliation(month=self.month, realm_id=self.realm_id)

        self.assertEqual(result["margin_flags"], 1)
        flag = Flag.objects.get(realm_id=self.realm_id, flag_type=FlagType.CONNECTWISE_MARGIN)
        self.assertIn("Flat Erosion Co", flag.reason)
        self.assertIn("margin", flag.reason.lower())

    def test_flat_fee_profitable_creates_no_margin_flag(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="flat_fee_profitable"
        )

        result = run_connectwise_reconciliation(month=self.month, realm_id=self.realm_id)

        self.assertEqual(result["margin_flags"], 0)
        self.assertFalse(
            Flag.objects.filter(
                realm_id=self.realm_id, flag_type=FlagType.CONNECTWISE_MARGIN
            ).exists()
        )

    def test_missing_mapping_creates_missing_mapping_flag(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="missing_mapping"
        )

        result = run_connectwise_reconciliation(month=self.month, realm_id=self.realm_id)

        self.assertEqual(result["missing_mappings"], 1)
        flag = Flag.objects.get(
            realm_id=self.realm_id, flag_type=FlagType.CONNECTWISE_MISSING_MAPPING
        )
        self.assertIn("Missing Mapping Co", flag.reason)
        self.assertEqual(flag.severity, Severity.MEDIUM)

    def test_reconciliation_is_idempotent(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="flat_fee_margin_erosion"
        )
        run_connectwise_reconciliation(month=self.month, realm_id=self.realm_id)
        first_count = Flag.objects.filter(realm_id=self.realm_id).count()

        result = run_connectwise_reconciliation(month=self.month, realm_id=self.realm_id)

        self.assertEqual(Flag.objects.filter(realm_id=self.realm_id).count(), first_count)
        self.assertEqual(result["margin_flags"], 1)

    def test_role_specific_burden_rate(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="flat_fee_profitable"
        )
        # A high role-specific burden rate pushes the previously-profitable client
        # below the target margin threshold, proving the role rate is used instead of
        # the global default.
        ConnectWiseWorkRole.objects.update_or_create(
            company=self.company,
            realm_id=self.realm_id,
            role_name="Engineer",
            defaults={"burden_rate": Decimal("650.00")},
        )

        result = run_connectwise_reconciliation(month=self.month, realm_id=self.realm_id)

        self.assertEqual(result["margin_flags"], 1)
        flag = Flag.objects.get(realm_id=self.realm_id, flag_type=FlagType.CONNECTWISE_MARGIN)
        self.assertIn("Flat Profitable Co", flag.reason)

    def test_unbilled_high_severity_for_large_leakage(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="hourly_leakage"
        )
        customer = QBCustomer.objects.get(realm_id=self.realm_id)
        self._create_invoice(customer, Decimal("100.00"))

        run_connectwise_reconciliation(month=self.month, realm_id=self.realm_id)

        flag = Flag.objects.get(realm_id=self.realm_id, flag_type=FlagType.CONNECTWISE_UNBILLED)
        self.assertEqual(flag.severity, Severity.HIGH)

    def test_mixed_scenario_summary_counts(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="mixed"
        )
        for customer in QBCustomer.objects.filter(realm_id=self.realm_id):
            self._create_invoice(customer, Decimal("100.00"))

        result = run_connectwise_reconciliation(month=self.month, realm_id=self.realm_id)

        self.assertEqual(result["clients_checked"], 3)
        self.assertEqual(result["missing_mappings"], 1)
        self.assertGreaterEqual(result["unbilled_flags"] + result["margin_flags"], 1)
