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
            ("--color-flag", "#A05E22"),
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


class ResponsiveAccessibilityTests(TestCase):
    """D6 — Responsive and accessibility pass."""

    @property
    def tokens_path(self) -> Path:
        return Path(settings.BASE_DIR) / "core" / "static" / "css" / "tokens.css"

    @property
    def css(self) -> str:
        return self.tokens_path.read_text(encoding="utf-8")

    def test_mobile_media_query_stacks_ledger_rows(self) -> None:
        css = self.css
        self.assertIn("@media (max-width: 640px)", css)
        # The media block should change the row direction to column.
        media_block = css.split("@media (max-width: 640px)", 1)[1].split("}", 1)[0]
        self.assertIn(".ledger-row", media_block)
        self.assertIn("flex-direction", media_block)

    def test_interactive_elements_have_visible_focus_outlines(self) -> None:
        css = self.css
        for selector in (".month-select:focus-visible", ".text-btn:focus-visible", ".notes-field:focus-visible"):
            self.assertIn(selector, css)
            block = css.split(selector, 1)[1].split("}", 1)[0]
            self.assertIn("outline", block)

    def _relative_luminance(self, hex_color: str) -> float:
        hex_color = hex_color.lstrip("#")
        r = int(hex_color[0:2], 16) / 255
        g = int(hex_color[2:4], 16) / 255
        b = int(hex_color[4:6], 16) / 255
        channels = []
        for c in (r, g, b):
            if c <= 0.03928:
                channels.append(c / 12.92)
            else:
                channels.append(((c + 0.055) / 1.055) ** 2.4)
        return 0.2126 * channels[0] + 0.7152 * channels[1] + 0.0722 * channels[2]

    def _contrast_ratio(self, fg: str, bg: str) -> float:
        lum1 = self._relative_luminance(fg)
        lum2 = self._relative_luminance(bg)
        lighter = max(lum1, lum2)
        darker = min(lum1, lum2)
        return (lighter + 0.05) / (darker + 0.05)

    def _token_value(self, name: str) -> str:
        import re

        match = re.search(rf"{re.escape(name)}:\s*(#[0-9A-Fa-f]{{6}})", self.css)
        if not match:
            self.fail(f"Could not find hex value for {name} in tokens.css")
        return match.group(1)

    def test_token_colors_meet_wcag_aa_against_paper(self) -> None:
        """Small text WCAG AA requires a contrast ratio of at least 4.5:1."""
        paper = self._token_value("--color-paper")
        for fg in (
            self._token_value("--color-ink"),
            self._token_value("--color-slate"),
            self._token_value("--color-flag"),
            self._token_value("--color-rejected"),
        ):
            ratio = self._contrast_ratio(fg, paper)
            self.assertGreaterEqual(
                ratio,
                4.5,
                f"{fg} on {paper} has contrast {ratio:.2f}:1, below WCAG AA 4.5:1",
            )


class SelfCritiqueTests(TestCase):
    """D7 — Self-critique pass against design-system constraints."""

    @property
    def tokens_path(self) -> Path:
        return Path(settings.BASE_DIR) / "core" / "static" / "css" / "tokens.css"

    @property
    def css(self) -> str:
        return self.tokens_path.read_text(encoding="utf-8")

    def setUp(self) -> None:
        from django.contrib.auth.models import User

        self.user = User.objects.create_user(username="reviewer", password="pass")
        self.client.login(username="reviewer", password="pass")

    def test_css_has_no_box_shadows_beyond_the_intentional_reset(self) -> None:
        for line in self.css.splitlines():
            if "box-shadow" in line:
                self.assertIn("none", line, f"Unexpected box-shadow rule: {line}")

    def test_css_has_no_border_radius_above_4px(self) -> None:
        import re

        for match in re.finditer(r"border-radius:\s*(\d+)px", self.css):
            radius = int(match.group(1))
            self.assertLessEqual(radius, 4, f"border-radius {radius}px exceeds 4px")

    def test_dashboard_markup_has_no_inline_styles_or_shadows(self) -> None:
        resp = self.client.get("/dashboard/", {"month": "2025-01"})
        content = resp.content.decode("utf-8")
        self.assertNotIn("box-shadow", content)
        self.assertNotIn("border-radius: 9999px", content)
        self.assertNotIn("border-radius: 50%", content)
