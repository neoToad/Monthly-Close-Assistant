"""Dockerization smoke tests (Prompt 15).

These tests verify that the Docker build and compose files are present and that the
Django settings can be driven from a single ``DATABASE_URL`` variable so the same
settings module works inside containers.
"""
from __future__ import annotations

import os
from importlib import reload
from pathlib import Path
from unittest.mock import patch

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class DockerAssetTests(SimpleTestCase):
    """Project-level Docker files exist."""

    def test_dockerfile_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "Dockerfile").is_file())

    def test_docker_compose_exists(self) -> None:
        self.assertTrue((REPO_ROOT / "docker-compose.yml").is_file())

    def test_dockerignore_exists(self) -> None:
        self.assertTrue((REPO_ROOT / ".dockerignore").is_file())


class DockerConfigTests(SimpleTestCase):
    """Settings can parse ``DATABASE_URL`` for the containerized Postgres service."""

    def test_database_url_overrides_individual_db_variables(self) -> None:
        url = "postgres://close_app:close_dev_pw@db:5432/close_assistant"
        with patch.dict(os.environ, {"DATABASE_URL": url}, clear=False):
            from close_assistant import settings

            reload(settings)

        db = settings.DATABASES["default"]
        self.assertEqual(db["ENGINE"], "django.db.backends.postgresql")
        self.assertEqual(db["NAME"], "close_assistant")
        self.assertEqual(db["USER"], "close_app")
        self.assertEqual(db["PASSWORD"], "close_dev_pw")
        self.assertEqual(db["HOST"], "db")
        self.assertEqual(db["PORT"], "5432")

    def test_database_url_is_optional(self) -> None:
        with patch.dict(os.environ, {"DATABASE_URL": ""}, clear=False):
            from close_assistant import settings

            reload(settings)

        self.assertIn("default", settings.DATABASES)
        self.assertEqual(
            settings.DATABASES["default"]["ENGINE"], "django.db.backends.postgresql"
        )
