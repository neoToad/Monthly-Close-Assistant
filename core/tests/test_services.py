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

    def test_partial_write_failure_records_successful_suggestions(self) -> None:
        from core.models import AccountReconciliationState

        token = mock.MagicMock(realm_id="realm-a")
        company = _make_bank_balance(ending_balance=Decimal("-100.00")).company
        suggestions_result = {
            "account_name": "Operating Checking",
            "statement_balance": Decimal("-100.00"),
            "posted_total": Decimal("-25.00"),
            "difference": Decimal("-75.00"),
            "suggestions": [
                {
                    "id": "sug-1",
                    "type": "journal_entry",
                    "description": "First fix",
                    "amount": "25.00",
                    "account_id": "qb-acc-1",
                    "lines": [],
                },
                {
                    "id": "sug-2",
                    "type": "journal_entry",
                    "description": "Second fix",
                    "amount": "50.00",
                    "account_id": "qb-acc-1",
                    "lines": [],
                },
            ],
        }
        AccountReconciliationState.objects.create(
            company=company,
            realm_id="realm-a",
            qb_account_id="qb-acc-1",
            month="2026-06",
            statement_balance=Decimal("-100.00"),
        )

        with mock.patch(
            "core.services.reconciliation.reconcile_agent.suggest_account_fixes",
            return_value=suggestions_result,
        ), mock.patch(
            "core.services.reconciliation.qb_tokens.get_active_token", return_value=token
        ), mock.patch(
            "core.services.reconciliation.qb_client.build_quickbooks_client"
        ), mock.patch(
            "core.services.reconciliation.qb_client.sync_transactions"
        ) as mock_sync, mock.patch(
            "core.services.reconciliation.run_reconciliation"
        ) as mock_run, mock.patch(
            "core.services.reconciliation.qb_writes.apply_suggestion",
            side_effect=[
                {"object_type": "JournalEntry", "id": "je-1", "amount": "25.00"},
                RuntimeError("second write failed"),
            ],
        ):
            result = apply_account_reconciliation_suggestions(
                month="2026-06",
                realm_id="realm-a",
                qb_account_id="qb-acc-1",
                suggestion_ids=["sug-1", "sug-2"],
                dry_run=False,
            )

        self.assertFalse(result["success"])
        self.assertEqual(result["created_objects"][0]["id"], "je-1")
        mock_sync.assert_not_called()
        mock_run.assert_not_called()

        state = AccountReconciliationState.objects.get(
            company=company,
            qb_account_id="qb-acc-1",
            month="2026-06",
        )
        self.assertEqual(state.applied_suggestions, ["sug-1"])

    def test_post_apply_sync_failure_is_reported_without_losing_success(self) -> None:
        token = mock.MagicMock(realm_id="realm-a")
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(amount=Decimal("-25.00"))

        with mock.patch(
            "core.services.reconciliation.qb_tokens.get_active_token", return_value=token
        ), mock.patch(
            "core.services.reconciliation.qb_client.build_quickbooks_client"
        ), mock.patch(
            "core.services.reconciliation.qb_client.sync_transactions",
            side_effect=RuntimeError("sync failed"),
        ), mock.patch(
            "core.services.reconciliation.run_reconciliation"
        ) as mock_run, mock.patch(
            "core.services.reconciliation.qb_writes.apply_suggestion",
            return_value={"object_type": "JournalEntry", "id": "je-1", "amount": "25.00"},
        ):
            result = apply_account_reconciliation_suggestions(
                month="2026-06",
                realm_id="realm-a",
                qb_account_id="qb-acc-1",
                suggestion_ids=["sug-1"],
                dry_run=False,
            )

        self.assertTrue(result["success"])
        self.assertEqual(result["sync_error"], "sync failed")
        self.assertIn("Applied 1 adjustment", result["notice"])
        mock_run.assert_called_once_with("2026-06", realm_id="realm-a")
