"""CI/CD workflow validation tests (Prompt 16).

These tests ensure the GitHub Actions workflow file exists and contains the jobs and
commands needed to verify the Dockerized app on every push and pull request.
"""
from __future__ import annotations

from pathlib import Path

from django.test import SimpleTestCase


REPO_ROOT = Path(__file__).resolve().parent.parent.parent


class CIWorkflowTests(SimpleTestCase):
    """The CI workflow file is present and wired to the right branches and jobs."""

    def test_workflow_file_exists(self) -> None:
        path = REPO_ROOT / ".github" / "workflows" / "ci.yml"
        self.assertTrue(path.is_file())

    def test_workflow_triggers_on_target_branches(self) -> None:
        text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("push:", text)
        self.assertIn("pull_request:", text)
        self.assertIn("feature/close-assistant-build", text)
        self.assertIn("main", text)

    def test_workflow_builds_and_tests_in_docker_compose(self) -> None:
        text = (REPO_ROOT / ".github" / "workflows" / "ci.yml").read_text(
            encoding="utf-8"
        )
        self.assertIn("docker compose build", text)
        self.assertIn("docker compose run", text)
        self.assertIn("python manage.py test", text)
