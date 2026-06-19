"""Tests for core service-layer orchestration.

These tests exercise ``core.services.reconciliation`` directly, without HTTP, to verify
that the account-reconciliation apply flow is callable from both the dashboard view
and the management command.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from core.services.reconciliation import apply_account_reconciliation_suggestions
from core.tests.test_management import _make_bank_balance, _make_bank_txn


class ApplyAccountReconciliationServiceTests(TestCase):
    def test_dry_run_returns_preview_without_qb_calls(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(amount=Decimal("-25.00"))

        result = apply_account_reconciliation_suggestions(
            month="2026-06",
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            suggestion_ids=["sug-1"],
            dry_run=True,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(len(result["preview_objects"]), 1)
        self.assertIn("Previewing 1 adjustment(s)", result["notice"])
        self.assertEqual(result["created_objects"], [])

    def test_dry_run_with_unknown_suggestion_is_empty_preview(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(amount=Decimal("-25.00"))

        result = apply_account_reconciliation_suggestions(
            month="2026-06",
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            suggestion_ids=["missing-id"],
            dry_run=True,
        )

        self.assertTrue(result["success"])
        self.assertTrue(result["dry_run"])
        self.assertEqual(result["selected"], [])
        self.assertEqual(result["preview_objects"], [])
        self.assertIn("No selected suggestions", result["notice"])

    def test_apply_without_token_reports_missing_connection(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(amount=Decimal("-25.00"))

        with mock.patch(
            "core.services.reconciliation.qb_tokens.get_active_token",
            return_value=None,
        ):
            result = apply_account_reconciliation_suggestions(
                month="2026-06",
                realm_id="realm-a",
                qb_account_id="qb-acc-1",
                suggestion_ids=["sug-1"],
                dry_run=False,
            )

        self.assertFalse(result["success"])
        self.assertTrue(result["token_missing"])
        self.assertIn("not connected", result["error"])
        self.assertEqual(result["created_objects"], [])

    def test_apply_writes_and_updates_state(self) -> None:
        from core.models import AccountReconciliationState, ReconciliationStatus

        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(amount=Decimal("-25.00"))
        token = mock.MagicMock(realm_id="realm-a")

        with mock.patch(
            "core.services.reconciliation.qb_tokens.get_active_token", return_value=token
        ), mock.patch(
            "core.services.reconciliation.qb_client.build_quickbooks_client"
        ) as mock_build, mock.patch.object(
            mock_build.return_value,
            "sync_transactions",
            return_value={"created": 0, "skipped": 0, "errors": 0},
        ), mock.patch(
            "core.services.reconciliation.qb_client.sync_transactions"
        ) as mock_sync, mock.patch(
            "core.services.reconciliation.qb_writes.apply_suggestion",
            return_value={"object_type": "JournalEntry", "id": "je-1", "amount": "25.00"},
        ) as mock_apply:
            result = apply_account_reconciliation_suggestions(
                month="2026-06",
                realm_id="realm-a",
                qb_account_id="qb-acc-1",
                suggestion_ids=["sug-1"],
                dry_run=False,
            )

        self.assertTrue(result["success"])
        self.assertFalse(result["dry_run"])
        self.assertEqual(len(result["created_objects"]), 1)
        mock_apply.assert_called_once()
        mock_sync.assert_called_once()

        state = AccountReconciliationState.objects.get(
            company__realm_id="realm-a",
            qb_account_id="qb-acc-1",
            month="2026-06",
        )
        self.assertIn("sug-1", state.applied_suggestions)
        self.assertEqual(state.status, ReconciliationStatus.IN_PROGRESS)

    def test_dry_run_is_idempotent(self) -> None:
        from core.models import AccountReconciliationState

        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(amount=Decimal("-25.00"))

        result1 = apply_account_reconciliation_suggestions(
            month="2026-06",
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            suggestion_ids=["sug-1"],
            dry_run=True,
        )
        state1 = AccountReconciliationState.objects.get(
            company__realm_id="realm-a",
            qb_account_id="qb-acc-1",
            month="2026-06",
        )

        result2 = apply_account_reconciliation_suggestions(
            month="2026-06",
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            suggestion_ids=["sug-1"],
            dry_run=True,
        )
        state2 = AccountReconciliationState.objects.get(
            company__realm_id="realm-a",
            qb_account_id="qb-acc-1",
            month="2026-06",
        )

        self.assertTrue(result1["success"])
        self.assertTrue(result2["success"])
        self.assertEqual(state1.id, state2.id)
        self.assertEqual(state1.status, state2.status)
        self.assertEqual(
            len(state1.last_suggestions["suggestions"]),
            len(state2.last_suggestions["suggestions"]),
        )

    def test_apply_is_idempotent_via_applied_suggestions(self) -> None:
        from core.models import AccountReconciliationState

        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(amount=Decimal("-25.00"))
        token = mock.MagicMock(realm_id="realm-a")

        with mock.patch(
            "core.services.reconciliation.qb_tokens.get_active_token", return_value=token
        ), mock.patch(
            "core.services.reconciliation.qb_client.build_quickbooks_client"
        ) as mock_build, mock.patch(
            "core.services.reconciliation.qb_client.sync_transactions"
        ) as mock_sync, mock.patch(
            "core.services.reconciliation.qb_writes.apply_suggestion",
            return_value={"object_type": "JournalEntry", "id": "je-1", "amount": "25.00"},
        ) as mock_apply:
            result1 = apply_account_reconciliation_suggestions(
                month="2026-06",
                realm_id="realm-a",
                qb_account_id="qb-acc-1",
                suggestion_ids=["sug-1"],
                dry_run=False,
            )
            self.assertTrue(result1["success"])
            self.assertEqual(len(result1["created_objects"]), 1)
            first_call_count = mock_apply.call_count

            result2 = apply_account_reconciliation_suggestions(
                month="2026-06",
                realm_id="realm-a",
                qb_account_id="qb-acc-1",
                suggestion_ids=["sug-1"],
                dry_run=False,
            )

        self.assertTrue(result2["success"])
        self.assertEqual(mock_apply.call_count, first_call_count)
        self.assertEqual(len(result2["created_objects"]), 0)
        self.assertIn("already applied", result2["notice"])

        state = AccountReconciliationState.objects.get(
            company__realm_id="realm-a",
            qb_account_id="qb-acc-1",
            month="2026-06",
        )
        self.assertEqual(state.applied_suggestions.count("sug-1"), 1)
