"""Tests for the ledger design system (Prompts D1–D7).

These tests verify the rendered templates and static CSS match the design-system
spec in docs/Monthly_Close_Assistant_Design_System_Prompts.md. They are written
TDD-style: each test asserts the structure that the next implementation step must
provide.
"""
from __future__ import annotations

from pathlib import Path

from django.conf import settings
from django.test import TestCase


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
