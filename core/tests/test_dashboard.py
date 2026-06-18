"""Tests for the HTMX review dashboard (Prompt 13).

Covers the dashboard view, flag approve/reject actions, and close-summary review.
Login requirements are tested separately in Prompt 14.
"""
from __future__ import annotations

import datetime as dt
from decimal import Decimal

from django.test import TestCase
from django.urls import reverse

from core.models import (
    CloseSummary,
    CloseSummaryStatus,
    Flag,
    FlagStatus,
    Transaction,
)


class DashboardViewTests(TestCase):
    def test_dashboard_renders_flags_and_summary(self) -> None:
        txn = Transaction.objects.create(
            date=dt.date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("100.00"),
            category="Office Supplies",
            qb_transaction_id="QB-1",
            source_type="Purchase",
        )
        flag = Flag.objects.create(
            flag_type="reconciliation",
            transaction=txn,
            reason="Amount mismatch",
            severity="high",
        )
        summary = CloseSummary.objects.create(
            month="2025-01",
            summary_text="Draft summary.",
            status=CloseSummaryStatus.DRAFT,
        )

        resp = self.client.get(reverse("core:dashboard"), {"month": "2025-01"})
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, flag.reason)
        self.assertContains(resp, summary.summary_text)
        self.assertContains(resp, "2025-01")

    def test_dashboard_hx_get_returns_partial_content(self) -> None:
        Transaction.objects.create(
            date=dt.date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("100.00"),
            category="Office Supplies",
            qb_transaction_id="QB-1",
            source_type="Purchase",
        )
        resp = self.client.get(
            reverse("core:dashboard"),
            {"month": "2025-01"},
            HTTP_HX_REQUEST="true",
        )
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "2025-01")

    def test_approve_flag_updates_status(self) -> None:
        txn = Transaction.objects.create(
            date=dt.date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("100.00"),
            qb_transaction_id="QB-1",
            source_type="Purchase",
        )
        flag = Flag.objects.create(
            flag_type="reconciliation",
            transaction=txn,
            reason="Amount mismatch",
            severity="high",
        )
        resp = self.client.post(reverse("core:flag_approve", args=[flag.id]))
        self.assertEqual(resp.status_code, 200)
        flag.refresh_from_db()
        self.assertEqual(flag.status, FlagStatus.APPROVED)
        self.assertContains(resp, flag.reason)

    def test_reject_flag_updates_status(self) -> None:
        txn = Transaction.objects.create(
            date=dt.date(2025, 1, 15),
            vendor="Acme Corp",
            amount=Decimal("100.00"),
            qb_transaction_id="QB-1",
            source_type="Purchase",
        )
        flag = Flag.objects.create(
            flag_type="reconciliation",
            transaction=txn,
            reason="Missing bank txn",
            severity="medium",
        )
        resp = self.client.post(reverse("core:flag_reject", args=[flag.id]))
        self.assertEqual(resp.status_code, 200)
        flag.refresh_from_db()
        self.assertEqual(flag.status, FlagStatus.REJECTED)

    def test_mark_summary_reviewed(self) -> None:
        summary = CloseSummary.objects.create(
            month="2025-01",
            summary_text="Draft summary.",
            status=CloseSummaryStatus.DRAFT,
        )
        resp = self.client.post(
            reverse("core:summary_review", args=[summary.month]),
            {"reviewer_notes": "Looks good."},
        )
        self.assertEqual(resp.status_code, 200)
        summary.refresh_from_db()
        self.assertEqual(summary.status, CloseSummaryStatus.REVIEWED)
        self.assertEqual(summary.reviewer_notes, "Looks good.")
        self.assertContains(resp, "Reviewed")
