"""Tests for the homepage and global navigation (Prompt 15).

Covers the landing-page view, authenticated redirect behavior, and the presence
of navigation links on key templates.
"""
from __future__ import annotations

from django.contrib.auth.models import User
from django.test import TestCase
from django.urls import reverse


class HomePageTests(TestCase):
    def test_home_renders_for_anonymous_user(self) -> None:
        """Anonymous visitors see the marketing-style landing page."""
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Monthly Close Assistant")
        self.assertContains(resp, "Log in to review")
        self.assertContains(resp, reverse("login"))

    def test_home_redirects_authenticated_user_to_dashboard(self) -> None:
        """Logged-in users skip the landing page and go straight to the dashboard."""
        user = User.objects.create_user(username="reviewer", password="pass")
        self.client.login(username="reviewer", password="pass")

        resp = self.client.get(reverse("core:home"))

        self.assertEqual(resp.status_code, 302)
        self.assertEqual(resp.url, reverse("core:dashboard"))


class NavigationTests(TestCase):
    def setUp(self) -> None:
        self.user = User.objects.create_user(username="reviewer", password="pass")

    def test_anonymous_nav_links(self) -> None:
        """Anonymous users see Admin and Log in links, not Dashboard or QB connect."""
        resp = self.client.get(reverse("core:home"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("login"))
        self.assertContains(resp, reverse("admin:index"))
        self.assertNotContains(resp, reverse("core:dashboard"))
        self.assertNotContains(resp, reverse("core:qb_oauth_start"))

    def test_authenticated_nav_links_on_dashboard(self) -> None:
        """Authenticated users see Dashboard, Connect QuickBooks, Admin, and Log out."""
        self.client.login(username="reviewer", password="pass")
        resp = self.client.get(reverse("core:dashboard"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, reverse("core:dashboard"))
        self.assertContains(resp, reverse("core:qb_oauth_start"))
        self.assertContains(resp, reverse("admin:index"))
        self.assertContains(resp, "Log out")

    def test_nav_appears_on_login_page(self) -> None:
        """The global header is included on the Django login template."""
        resp = self.client.get(reverse("login"))
        self.assertEqual(resp.status_code, 200)
        self.assertContains(resp, "Close Assistant")
        self.assertContains(resp, reverse("admin:index"))
        self.assertContains(resp, reverse("login"))
