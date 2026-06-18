"""Tests for the close-summary agent (Prompt 10).

The agent is exercised against a deterministic fallback (no live Anthropic API
calls in tests). A fake LLM client is also used to verify the LangChain/LangGraph
integration path.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal
from unittest import mock

from django.test import TestCase

from core.models import CloseSummary, CloseSummaryStatus, Flag, FlagType, Severity, Transaction


def _make_txn(**overrides) -> Transaction:
    defaults = dict(
        date=dt.date(2025, 1, 15),
        vendor="Acme Corp",
        amount=Decimal("100.00"),
        category="Office Supplies",
        gl_account="5000 - Supplies",
        qb_transaction_id="QB-1",
    )
    defaults.update(overrides)
    return Transaction.objects.create(**defaults)


class GatherInputsTests(TestCase):
    def test_gather_inputs_includes_category_totals_and_open_flags(self) -> None:
        from core.agent.summary import gather_inputs

        _make_txn(qb_transaction_id="QB-A", category="Software", amount=Decimal("200.00"))
        _make_txn(qb_transaction_id="QB-B", category="Software", amount=Decimal("300.00"))
        _make_txn(qb_transaction_id="QB-C", category="Office Supplies", amount=Decimal("100.00"))

        inputs = gather_inputs("2025-01")
        self.assertEqual(inputs["category_totals"]["Software"], Decimal("500.00"))
        self.assertEqual(inputs["category_totals"]["Office Supplies"], Decimal("100.00"))

    def test_gather_inputs_includes_open_flags_only(self) -> None:
        from core.agent.summary import gather_inputs

        txn = _make_txn()
        Flag.objects.create(
            flag_type=FlagType.RECONCILIATION,
            transaction=txn,
            reason="Amount mismatch",
            severity=Severity.HIGH,
        )
        Flag.objects.create(
            flag_type=FlagType.ANOMALY,
            transaction=txn,
            reason="Duplicate",
            severity=Severity.MEDIUM,
            status="rejected",
        )
        inputs = gather_inputs("2025-01")
        reasons = [f["reason"] for f in inputs["open_flags"]]
        self.assertIn("Amount mismatch", reasons)
        self.assertNotIn("Duplicate", reasons)


class DraftCloseSummaryTests(TestCase):
    def test_creates_draft_summary_without_api_key(self) -> None:
        """With no ANTHROPIC_API_KEY, the agent falls back to a deterministic summary."""
        from core.agent.summary import draft_close_summary

        _make_txn(qb_transaction_id="QB-1", category="Software", amount=Decimal("250.00"))
        summary = draft_close_summary("2025-01")
        self.assertEqual(summary.month, "2025-01")
        self.assertEqual(summary.status, CloseSummaryStatus.DRAFT)
        self.assertIn("2025-01", summary.summary_text)
        self.assertIn("Software", summary.summary_text)

    def test_re_running_updates_existing_summary(self) -> None:
        from core.agent.summary import draft_close_summary

        _make_txn(qb_transaction_id="QB-1")
        first = draft_close_summary("2025-01")
        second = draft_close_summary("2025-01")
        self.assertEqual(CloseSummary.objects.count(), 1)
        self.assertEqual(second.id, first.id)

    def test_uses_provided_llm_client_when_available(self) -> None:
        """A fake LLM client can be injected for testing or custom behavior."""
        from core.agent.summary import draft_close_summary

        _make_txn(qb_transaction_id="QB-1", category="Office Supplies")
        fake_llm = mock.MagicMock()
        fake_llm.invoke.return_value = mock.MagicMock(content="AI-generated summary.")
        summary = draft_close_summary("2025-01", llm=fake_llm)
        self.assertIn("AI-generated summary.", summary.summary_text)
        fake_llm.invoke.assert_called_once()
