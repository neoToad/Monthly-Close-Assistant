"""Tests for the ledger design system (Prompts D1–D7).

These tests verify the rendered templates and static CSS match the design-system
spec in docs/Monthly_Close_Assistant_Design_System_Prompts.md. They are written
TDD-style: each test asserts the structure that the next implementation step must
provide.
"""
from __future__ import annotations

import datetime as dt
from pathlib import Path

from django.conf import settings
from django.test import TestCase

from core.models import CloseSummary


class DesignTokenTests(TestCase):
    """D1 — Design tokens and base styles."""

    @property
    def tokens_path(self) -> Path:
        return Path(settings.BASE_DIR) / "core" / "static" / "css" / "tokens.css"

    def test_tokens_css_exists(self) -> None:
        self.assertTrue(
            self.tokens_path.exists(),
            "tokens.css should exist at core/static/css/tokens.css",
        )

    def test_tokens_css_declares_colors(self) -> None:
        css = self.tokens_path.read_text(encoding="utf-8")
        for token, value in (
            ("--color-ink", "#1C2B3A"),
            ("--color-paper", "#F7F5F0"),
            ("--color-slate", "#5B6B7A"),
            ("--color-flag", "#C9762B"),
            ("--color-confirmed", "#3A6B4C"),
            ("--color-rejected", "#8B3A3A"),
            ("--color-hairline", "#DDD8CC"),
        ):
            self.assertIn(token, css)
            self.assertIn(value, css)

    def test_tokens_css_declares_typography(self) -> None:
        css = self.tokens_path.read_text(encoding="utf-8")
        self.assertIn('--font-display: "Source Serif 4"', css)
        self.assertIn('--font-body: "IBM Plex Sans"', css)
        for token in ("--text-xs", "--text-sm", "--text-base", "--text-lg", "--text-xl", "--text-2xl"):
            self.assertIn(token, css)

    def test_tokens_css_declares_spacing_scale(self) -> None:
        css = self.tokens_path.read_text(encoding="utf-8")
        for i in range(1, 9):
            self.assertIn(f"--space-{i}", css)

    def test_base_html_links_google_fonts(self) -> None:
        """The login page extends base.html, so its markup proves the global head."""
        resp = self.client.get("/accounts/login/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("fonts.googleapis.com", content)
        self.assertIn("Source+Serif+4", content)
        self.assertIn("IBM+Plex+Sans", content)
        self.assertIn("display=swap", content)

    def test_base_html_links_tokens_css(self) -> None:
        resp = self.client.get("/accounts/login/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("tokens.css", content)


class DashboardHeaderTests(TestCase):
    """D2 — Page shell and ledger header."""

    def setUp(self) -> None:
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(username="reviewer", password="pass")
        self.client.login(username="reviewer", password="pass")

    def _create_flag(self, status: str, vendor: str = "Acme Corp", amount: str = "100.00") -> Flag:
        from decimal import Decimal

        from core.models import Flag, FlagStatus, Transaction

        counter = getattr(self, "_flag_counter", 0) + 1
        self._flag_counter = counter
        txn = Transaction.objects.create(
            date=dt.date(2025, 1, 15),
            vendor=vendor,
            amount=Decimal(amount),
            qb_transaction_id=f"QB-{counter}-{vendor}",
            source_type="Purchase",
        )
        return Flag.objects.create(
            flag_type="reconciliation",
            transaction=txn,
            reason=f"{status} flag",
            severity="medium",
            status=getattr(FlagStatus, status.upper()),
        )

    def test_dashboard_header_has_title_and_month_selector(self) -> None:
        resp = self.client.get("/dashboard/", {"month": "2025-01"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("ledger-header", content)
        self.assertIn("Close Assistant", content)
        self.assertIn('class="ledger-title"', content)
        self.assertIn('select', content)
        self.assertIn('id="month-select"', content)

    def test_status_strip_shows_open_approved_rejected_counts(self) -> None:
        self._create_flag("open")
        self._create_flag("open")
        self._create_flag("approved")
        self._create_flag("rejected")

        resp = self.client.get("/dashboard/", {"month": "2025-01"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("status-strip", content)
        self.assertIn("2 open", content)
        self.assertIn("1 approved", content)
        self.assertIn("1 rejected", content)


class LedgerRowTests(TestCase):
    """D3 — Flagged items table redesign."""

    def setUp(self) -> None:
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(username="reviewer", password="pass")
        self.client.login(username="reviewer", password="pass")

    def _create_flag(self, status: str = "open", vendor: str = "Acme Corp", amount: str = "123.45") -> Flag:
        from decimal import Decimal

        from core.models import Flag, FlagStatus, Transaction

        counter = getattr(self, "_flag_counter", 0) + 1
        self._flag_counter = counter
        txn = Transaction.objects.create(
            date=dt.date(2025, 1, 15),
            vendor=vendor,
            amount=Decimal(amount),
            qb_transaction_id=f"QB-{counter}-{vendor}",
            source_type="Purchase",
        )
        return Flag.objects.create(
            flag_type="reconciliation",
            transaction=txn,
            reason="Amount mismatch",
            severity="medium",
            status=getattr(FlagStatus, status.upper()),
        )

    def test_open_row_shows_vendor_reason_amount_and_status_dot(self) -> None:
        flag = self._create_flag()
        resp = self.client.get("/dashboard/", {"month": "2025-01"})
        content = resp.content.decode("utf-8")
        self.assertIn("ledger-row", content)
        self.assertIn("Acme Corp", content)
        self.assertIn("Amount mismatch", content)
        self.assertIn("$123.45", content)
        self.assertIn('class="dot flag"', content)
        self.assertIn("Open", content)

    def test_open_row_has_plain_text_action_buttons(self) -> None:
        flag = self._create_flag()
        resp = self.client.get("/dashboard/", {"month": "2025-01"})
        content = resp.content.decode("utf-8")
        self.assertIn('class="text-btn approve"', content)
        self.assertIn('class="text-btn reject"', content)
        self.assertNotIn('class="primary"', content)

    def test_approved_row_replaces_actions_with_confirmed_status(self) -> None:
        flag = self._create_flag()
        resp = self.client.post(f"/dashboard/flag/{flag.id}/approve/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Approved", content)
        self.assertIn('class="dot confirmed"', content)
        self.assertNotIn('class="text-btn approve"', content)
        self.assertNotIn('class="text-btn reject"', content)

    def test_rejected_row_replaces_actions_with_rejected_status(self) -> None:
        flag = self._create_flag()
        resp = self.client.post(f"/dashboard/flag/{flag.id}/reject/")
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("Rejected", content)
        self.assertIn('class="dot rejected"', content)
        self.assertNotIn('class="text-btn approve"', content)
        self.assertNotIn('class="text-btn reject"', content)


class CloseSummaryTests(TestCase):
    """D4 — Draft summary section redesign."""

    def setUp(self) -> None:
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(username="reviewer", password="pass")
        self.client.login(username="reviewer", password="pass")

    def _create_summary(self, status: str = "draft") -> CloseSummary:
        from core.models import CloseSummary, CloseSummaryStatus

        return CloseSummary.objects.create(
            month="2025-01",
            summary_text="This month shows a $2.00 discrepancy likely due to timing.",
            status=getattr(CloseSummaryStatus, status.upper()),
        )

    def test_summary_section_has_eyebrow_month_and_readable_text(self) -> None:
        self._create_summary()
        resp = self.client.get("/dashboard/", {"month": "2025-01"})
        content = resp.content.decode("utf-8")
        self.assertIn("DRAFT SUMMARY", content)
        self.assertIn('class="eyebrow"', content)
        self.assertIn('class="summary-month"', content)
        self.assertIn("2025-01", content)
        self.assertIn('class="summary-text"', content)

    def test_summary_section_has_plain_text_mark_reviewed_and_notes_field(self) -> None:
        self._create_summary()
        resp = self.client.get("/dashboard/", {"month": "2025-01"})
        content = resp.content.decode("utf-8")
        self.assertIn('class="summary-footer"', content)
        self.assertIn('class="text-btn approve"', content)
        self.assertIn("Mark Reviewed", content)
        self.assertIn('class="notes-field"', content)
        self.assertIn("reviewer_notes", content)

    def test_reviewed_summary_hides_form_and_shows_notes(self) -> None:
        summary = self._create_summary("reviewed")
        summary.reviewer_notes = "Looks good."
        summary.save()

        resp = self.client.get("/dashboard/", {"month": "2025-01"})
        content = resp.content.decode("utf-8")
        self.assertIn("Looks good.", content)
        self.assertNotIn("Mark Reviewed", content)
        self.assertNotIn('class="notes-field"', content)


class EmptyAndLoadingStateTests(TestCase):
    """D5 — Empty and loading states."""

    def setUp(self) -> None:
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(username="reviewer", password="pass")
        self.client.login(username="reviewer", password="pass")

    def test_empty_month_shows_empty_state_message(self) -> None:
        resp = self.client.get("/dashboard/", {"month": "2025-01"})
        self.assertEqual(resp.status_code, 200)
        content = resp.content.decode("utf-8")
        self.assertIn("empty-state", content)
        self.assertIn("No items flagged for 2025-01", content)
        self.assertIn("Everything reconciled cleanly", content)

    def test_tokens_css_has_htmx_request_loading_state(self) -> None:
        css = (Path(settings.BASE_DIR) / "core" / "static" / "css" / "tokens.css").read_text(encoding="utf-8")
        self.assertIn(".htmx-request", css)
        self.assertIn("opacity: 0.5", css)
