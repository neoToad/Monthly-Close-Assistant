"""Tests for the project scaffold (Prompt 1 — Project Scaffolding).

These guard the spec-driven configuration of the ``close_assistant`` Django project:

* PostgreSQL configured from environment variables (DB_NAME, DB_USER, DB_PASSWORD,
  DB_HOST, DB_PORT) loaded via python-decouple.
* ``django_htmx`` installed and wired in (INSTALLED_APPS + HtmxMiddleware).
* HTMX wired into a ``base.html`` template.
* ``.env.example`` listing every required variable.

They are ``SimpleTestCase``-based because the scaffold configuration does not require
database access; real Postgres connectivity is verified separately via
``manage.py migrate`` and by the model tests in Prompt 2.
"""
from __future__ import annotations

from django.conf import settings
from django.template.loader import get_template
from django.test import SimpleTestCase

from decouple import config

REPO_ROOT = settings.BASE_DIR


class InstalledAppsTests(SimpleTestCase):
    def test_core_app_is_installed(self) -> None:
        self.assertIn("core", settings.INSTALLED_APPS)

    def test_django_htmx_is_installed(self) -> None:
        self.assertIn("django_htmx", settings.INSTALLED_APPS)


class MiddlewareTests(SimpleTestCase):
    def test_htmx_middleware_present(self) -> None:
        middlewares = [m.lower() for m in settings.MIDDLEWARE]
        self.assertTrue(
            any("htmx" in m for m in middlewares),
            f"HtmxMiddleware not found in MIDDLEWARE: {settings.MIDDLEWARE}",
        )


class DatabaseConfigTests(SimpleTestCase):
    """PostgreSQL must be configured from env vars via python-decouple.

    Using ``.get()`` so that the default (sqlite) scaffold fails with clean
    AssertionErrors rather than KeyErrors before the Postgres config is implemented.
    """

    def test_postgres_engine(self) -> None:
        engine = settings.DATABASES["default"]["ENGINE"]
        self.assertTrue(
            engine.endswith("postgresql"),
            f"Expected a postgres engine, got {engine!r}",
        )

    def test_db_name_from_env(self) -> None:
        # The test runner prefixes the DB name with "test_" when it creates the
        # test database, so strip that to compare against the configured value.
        name = settings.DATABASES["default"].get("NAME", "")
        self.assertEqual(name.removeprefix("test_"), config("DB_NAME"))

    def test_db_user_from_env(self) -> None:
        self.assertEqual(settings.DATABASES["default"].get("USER"), config("DB_USER"))

    def test_db_password_from_env(self) -> None:
        self.assertEqual(
            settings.DATABASES["default"].get("PASSWORD"), config("DB_PASSWORD")
        )

    def test_db_host_from_env(self) -> None:
        self.assertEqual(settings.DATABASES["default"].get("HOST"), config("DB_HOST"))

    def test_db_port_from_env(self) -> None:
        self.assertEqual(settings.DATABASES["default"].get("PORT"), config("DB_PORT"))


class BaseTemplateTests(SimpleTestCase):
    def test_base_html_exists_parses_and_wires_htmx(self) -> None:
        # get_template raises TemplateDoesNotExist / TemplateSyntaxError on failure,
        # so a successful render proves the template exists, parses, and renders.
        rendered = get_template("base.html").render({})
        self.assertIn("<!DOCTYPE html>", rendered)
        self.assertIn("htmx.org", rendered)


class EnvExampleTests(SimpleTestCase):
    def test_env_example_lists_required_vars(self) -> None:
        env_example = (REPO_ROOT / ".env.example").read_text(encoding="utf-8")
        for var in (
            "SECRET_KEY",
            "DEBUG",
            "DB_NAME",
            "DB_USER",
            "DB_PASSWORD",
            "DB_HOST",
            "DB_PORT",
            "QB_CLIENT_ID",
            "QB_CLIENT_SECRET",
            "QB_REDIRECT_URI",
            "QB_SANDBOX_COMPANY_ID",
            "QB_ENVIRONMENT",
            "QB_TOKEN_REFRESH_BUFFER_MINUTES",
            "QB_TOKEN_ENCRYPTION_KEY",
        ):
            self.assertIn(var, env_example, f"{var} missing from .env.example")