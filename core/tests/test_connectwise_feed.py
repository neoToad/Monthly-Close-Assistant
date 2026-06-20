"""Tests for the synthetic ConnectWise feed generator (Step 3)."""
from __future__ import annotations

from django.test import TestCase
from django.utils import timezone

from core.common.dates import month_bounds
from core.engines import generate_connectwise_feed
from core.models import (
    BillingModel,
    ClientMapping,
    ConnectWiseCompany,
    ConnectWiseWorkRole,
    ExpenseEntry,
    ProductEntry,
    QuickBooksCompany,
    QBCustomer,
    TimeEntry,
)


class ConnectWiseFeedGeneratorTests(TestCase):
    """End-to-end tests for generate_connectwise_feed."""

    def setUp(self) -> None:
        self.month = "2025-01"
        self.realm_id = "realm-cw-test"
        self.company = QuickBooksCompany.objects.for_realm(self.realm_id, "Test CW Company")

    def _assert_dates_in_month(self) -> None:
        first, last = month_bounds(self.month)
        for model in (TimeEntry, ExpenseEntry, ProductEntry):
            for entry in model.objects.filter(realm_id=self.realm_id):
                self.assertGreaterEqual(entry.date, first)
                self.assertLessEqual(entry.date, last)

    def test_hourly_leakage_creates_activity_rows(self) -> None:
        result = generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="hourly_leakage"
        )

        self.assertEqual(result["scenario"], "hourly_leakage")
        self.assertEqual(result["companies_created"], 1)
        self.assertEqual(result["mappings_created"], 1)
        self.assertGreater(result["time_entries_created"], 0)
        self.assertGreater(result["expense_entries_created"], 0)
        self.assertEqual(result["product_entries_created"], 0)

        cw_company = ConnectWiseCompany.objects.get(realm_id=self.realm_id)
        mapping = ClientMapping.objects.get(realm_id=self.realm_id)
        self.assertEqual(mapping.connectwise_company, cw_company)
        self.assertEqual(mapping.billing_model, BillingModel.HOURLY)
        self.assertTrue(mapping.qbo_customer.name)
        self._assert_dates_in_month()

    def test_flat_fee_profitable_creates_flat_fee_mapping(self) -> None:
        result = generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="flat_fee_profitable"
        )

        self.assertEqual(result["companies_created"], 1)
        self.assertEqual(result["mappings_created"], 1)
        mapping = ClientMapping.objects.get(realm_id=self.realm_id)
        self.assertEqual(mapping.billing_model, BillingModel.FLAT_FEE)
        self.assertIsNotNone(mapping.flat_fee_amount)
        self.assertGreater(mapping.flat_fee_amount, 0)
        self._assert_dates_in_month()

    def test_missing_mapping_scenario_has_no_mapping(self) -> None:
        result = generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="missing_mapping"
        )

        self.assertEqual(result["companies_created"], 1)
        self.assertEqual(result["mappings_created"], 0)
        self.assertTrue(ConnectWiseCompany.objects.filter(realm_id=self.realm_id).exists())
        self.assertFalse(ClientMapping.objects.filter(realm_id=self.realm_id).exists())
        self.assertGreater(result["time_entries_created"], 0)

    def test_mixed_scenario_creates_multiple_clients(self) -> None:
        result = generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="mixed"
        )

        self.assertGreaterEqual(result["companies_created"], 2)
        mappings = ClientMapping.objects.filter(realm_id=self.realm_id)
        self.assertGreaterEqual(mappings.count(), 1)
        billing_models = set(mappings.values_list("billing_model", flat=True))
        self.assertTrue(billing_models.issubset({BillingModel.HOURLY, BillingModel.FLAT_FEE, BillingModel.RETAINER}))
        self._assert_dates_in_month()

    def test_force_overwrites_existing_feed(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="hourly_leakage"
        )
        first_count = TimeEntry.objects.filter(realm_id=self.realm_id).count()

        result = generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="flat_fee_profitable", force=True
        )

        self.assertEqual(result["companies_created"], 1)
        self.assertNotEqual(
            TimeEntry.objects.filter(realm_id=self.realm_id).count(),
            first_count,
        )
        self.assertTrue(
            ClientMapping.objects.filter(
                realm_id=self.realm_id, billing_model=BillingModel.FLAT_FEE
            ).exists()
        )

    def test_without_force_raises_when_data_exists(self) -> None:
        generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="hourly_leakage"
        )

        with self.assertRaises(ValueError):
            generate_connectwise_feed(
                month=self.month, realm_id=self.realm_id, scenario="flat_fee_profitable"
            )

    def test_seed_produces_reproducible_output(self) -> None:
        result_a = generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="mixed", seed=42
        )
        ids_a = list(
            TimeEntry.objects.filter(realm_id=self.realm_id)
            .order_by("connectwise_entry_id")
            .values_list("connectwise_entry_id", "hours")
        )

        # Delete all ConnectWise-related rows so the second run starts from the same state.
        TimeEntry.objects.filter(realm_id=self.realm_id).delete()
        ExpenseEntry.objects.filter(realm_id=self.realm_id).delete()
        ProductEntry.objects.filter(realm_id=self.realm_id).delete()
        ClientMapping.objects.filter(realm_id=self.realm_id).delete()
        QBCustomer.objects.filter(realm_id=self.realm_id).delete()
        ConnectWiseWorkRole.objects.filter(realm_id=self.realm_id).delete()
        ConnectWiseCompany.objects.filter(realm_id=self.realm_id).delete()

        result_b = generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="mixed", seed=42
        )
        ids_b = list(
            TimeEntry.objects.filter(realm_id=self.realm_id)
            .order_by("connectwise_entry_id")
            .values_list("connectwise_entry_id", "hours")
        )

        self.assertEqual(result_a, result_b)
        self.assertEqual(ids_a, ids_b)

    def test_idempotency_for_same_scenario(self) -> None:
        result_first = generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="flat_fee_margin_erosion"
        )
        result_second = generate_connectwise_feed(
            month=self.month, realm_id=self.realm_id, scenario="flat_fee_margin_erosion", force=True
        )

        # Master data is updated in place on the second run; activity rows are replaced.
        self.assertEqual(
            result_first["time_entries_created"], result_second["time_entries_created"]
        )
        self.assertEqual(
            result_first["expense_entries_created"], result_second["expense_entries_created"]
        )
        self.assertEqual(
            result_first["product_entries_created"], result_second["product_entries_created"]
        )


class ConnectWiseFeedCommandTests(TestCase):
    """Tests for the generate_connectwise_feed management command."""

    def test_command_prints_summary(self) -> None:
        from io import StringIO

        from django.core.management import call_command

        out = StringIO()
        err = StringIO()
        call_command(
            "generate_connectwise_feed",
            "2025-02",
            realm_id="realm-cmd",
            scenario="hourly_leakage",
            stdout=out,
            stderr=err,
        )
        output = out.getvalue()
        self.assertIn("ConnectWise feed generated", output)
        self.assertIn("scenario=hourly_leakage", output)
        self.assertIn("Time entries", output)
