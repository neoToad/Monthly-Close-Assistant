"""Deployment documentation validation tests (Prompt 17).

These tests ensure the Railway deployment guide exists and contains the expected
keywords and caveats.
"""
from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class RailwayDeployDocTests(SimpleTestCase):
    """The Railway deployment doc is present and mentions required setup."""

    def test_deploy_doc_exists(self) -> None:
        path = REPO_ROOT / "docs" / "DEPLOY.md"
        self.assertTrue(path.is_file())

    def test_deploy_doc_mentions_railway(self) -> None:
        text = (REPO_ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
        self.assertIn("Railway", text)

    def test_deploy_doc_lists_required_env_vars(self) -> None:
        text = (REPO_ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
        for var in (
            "SECRET_KEY",
            "DATABASE_URL",
            "CELERY_BROKER_URL",
            "ALLOWED_HOSTS",
        ):
            self.assertIn(var, text)

    def test_deploy_doc_notes_not_exercised_without_credentials(self) -> None:
        text = (REPO_ROOT / "docs" / "DEPLOY.md").read_text(encoding="utf-8")
        self.assertIn("not exercised", text)
