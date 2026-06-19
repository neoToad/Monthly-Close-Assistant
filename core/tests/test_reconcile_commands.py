"""Tests for AI-assisted reconciliation management commands.

Covers ``suggest_account_fixes`` and ``apply_account_fix``.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from io import StringIO
from unittest import mock

from django.core.management import call_command
from django.core.management.base import CommandError
from django.test import TestCase

from core.tests.test_management import _make_bank_balance, _make_bank_txn


def _fake_token(realm_id: str = "realm-a"):
    token = mock.MagicMock()
    token.realm_id = realm_id
    return token


class SuggestAccountFixesCommandTests(TestCase):
    def test_no_data_prints_warning(self) -> None:
        out = StringIO()
        call_command(
            "suggest_account_fixes",
            "2026-06",
            "--realm-id", "realm-a",
            "--account-id", "qb-acc-1",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("No suggestions generated", output)

    def test_prints_generated_suggestions(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(date=dt.date(2026, 6, 15), amount=Decimal("-25.00"))

        out = StringIO()
        call_command(
            "suggest_account_fixes",
            "2026-06",
            "--realm-id", "realm-a",
            "--account-id", "qb-acc-1",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Account:", output)
        self.assertIn("Month:", output)
        self.assertIn("2 suggestion(s)", output)
        self.assertIn("sug-1", output)
        self.assertIn("deposit", output)
        self.assertIn("journal_entry", output)

    def test_apply_executes_highest_confidence_suggestions(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(date=dt.date(2026, 6, 15), amount=Decimal("-25.00"))

        out = StringIO()
        token = _fake_token("realm-a")
        with mock.patch(
            "core.quickbooks.tokens.get_active_token", return_value=token
        ):
            with mock.patch("core.quickbooks.client.build_quickbooks_client"):
                with mock.patch(
                    "core.quickbooks.writes.apply_suggestion",
                    return_value={
                        "object_type": "Purchase",
                        "id": "QB-P-1",
                        "amount": "25.00",
                    },
                ) as mock_apply:
                    call_command(
                        "suggest_account_fixes",
                        "2026-06",
                        "--realm-id", "realm-a",
                        "--account-id", "qb-acc-1",
                        "--apply",
                        stdout=out,
                    )

        output = out.getvalue()
        self.assertIn("Applied 1 adjustment(s)", output)
        self.assertEqual(mock_apply.call_count, 1)

    def test_apply_respects_confidence_filter(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(date=dt.date(2026, 6, 15), amount=Decimal("-25.00"))

        out = StringIO()
        call_command(
            "suggest_account_fixes",
            "2026-06",
            "--realm-id", "realm-a",
            "--account-id", "qb-acc-1",
            "--apply",
            "--confidence", "high",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("No suggestions matched the confidence threshold", output)

    def test_apply_requires_quickbooks_connection(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(date=dt.date(2026, 6, 15), amount=Decimal("-25.00"))

        out = StringIO()
        with mock.patch(
            "core.quickbooks.tokens.get_active_token", return_value=None
        ):
            with self.assertRaises(CommandError):
                call_command(
                    "suggest_account_fixes",
                    "2026-06",
                    "--realm-id", "realm-a",
                    "--account-id", "qb-acc-1",
                    "--apply",
                    stdout=out,
                )


class ApplyAccountFixCommandTests(TestCase):
    def test_preview_dry_run_without_apply(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(date=dt.date(2026, 6, 15), amount=Decimal("-25.00"))

        out = StringIO()
        call_command(
            "apply_account_fix",
            "2026-06",
            "--realm-id", "realm-a",
            "--account-id", "qb-acc-1",
            "--suggestion-id", "sug-1",
            stdout=out,
        )
        output = out.getvalue()
        self.assertIn("Preview (dry run)", output)
        self.assertIn("Type:", output)
        self.assertIn("deposit", output)

    def test_missing_suggestion_id_raises_error(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(date=dt.date(2026, 6, 15), amount=Decimal("-25.00"))

        out = StringIO()
        with self.assertRaises(CommandError):
            call_command(
                "apply_account_fix",
                "2026-06",
                "--realm-id", "realm-a",
                "--account-id", "qb-acc-1",
                "--suggestion-id", "missing-id",
                stdout=out,
            )

    def test_apply_executes_write(self) -> None:
        _make_bank_balance(ending_balance=Decimal("-100.00"))
        _make_bank_txn(date=dt.date(2026, 6, 15), amount=Decimal("-25.00"))

        out = StringIO()
        token = _fake_token("realm-a")
        with mock.patch(
            "core.quickbooks.tokens.get_active_token", return_value=token
        ):
            with mock.patch("core.quickbooks.client.build_quickbooks_client"):
                with mock.patch(
                    "core.quickbooks.writes.apply_suggestion",
                    return_value={
                        "object_type": "Purchase",
                        "id": "QB-P-1",
                        "amount": "25.00",
                    },
                ) as mock_apply:
                    call_command(
                        "apply_account_fix",
                        "2026-06",
                        "--realm-id", "realm-a",
                        "--account-id", "qb-acc-1",
                        "--suggestion-id", "sug-1",
                        "--apply",
                        stdout=out,
                    )

        output = out.getvalue()
        self.assertIn("Created Purchase QB-P-1 for $25.00", output)
        mock_apply.assert_called_once()
