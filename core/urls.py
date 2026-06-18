"""URL configuration for the ``core`` app (Prompt 3 — QuickBooks OAuth).

Wires the two-step Intuit OAuth 2.0 authorization-code flow:

* ``quickbooks/oauth/start/`` → ``qb_oauth_start`` (redirect to Intuit).
* ``quickbooks/oauth/callback/`` → ``qb_oauth_callback`` (receive code, store tokens).
"""
from __future__ import annotations

from django.urls import path

from core import views

app_name = "core"

urlpatterns = [
    path("quickbooks/oauth/start/", views.qb_oauth_start, name="qb_oauth_start"),
    path("quickbooks/oauth/callback/", views.qb_oauth_callback, name="qb_oauth_callback"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/flag/<int:flag_id>/approve/", views.flag_approve, name="flag_approve"),
    path("dashboard/flag/<int:flag_id>/reject/", views.flag_reject, name="flag_reject"),
    path("dashboard/summary/<str:month>/review/", views.summary_review, name="summary_review"),
]