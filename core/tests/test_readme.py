"""README validation tests (Prompt 18).

These tests ensure the project README exists and contains the sections a new contributor
or deployer needs.
"""
from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class ReadmeTests(SimpleTestCase):
    """The root README is present and covers the essential topics."""

    def test_readme_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "README.md").is_file())

    def test_readme_has_key_sections(self) -> None:
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for heading in (
            "Monthly Close Assistant",
            "Features",
            "Architecture",
            "Local setup",
            "Running tests",
            "Management commands",
            "Dashboard",
            "Deployment",
        ):
            self.assertIn(heading, text)

    def test_readme_mentions_docker_and_railway(self) -> None:
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        self.assertIn("Docker", text)
        self.assertIn("Railway", text)

    def test_readme_lists_required_env_vars(self) -> None:
        text = (REPO_ROOT / "README.md").read_text(encoding="utf-8")
        for var in (
            "SECRET_KEY",
            "DATABASE_URL",
            "CELERY_BROKER_URL",
            "QB_CLIENT_ID",
        ):
            self.assertIn(var, text)
