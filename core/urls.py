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
    path("", views.home, name="home"),
    path("quickbooks/oauth/start/", views.qb_oauth_start, name="qb_oauth_start"),
    path("quickbooks/oauth/callback/", views.qb_oauth_callback, name="qb_oauth_callback"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("dashboard/sync/", views.qb_sync_now, name="qb_sync_now"),
    path("dashboard/reconcile/", views.reconcile_month, name="reconcile_month"),
    path("dashboard/bank-feed/generate/", views.generate_bank_feed_view, name="generate_bank_feed"),
    path("dashboard/connectwise/reconcile/", views.connectwise_reconciliation_view, name="connectwise_reconcile"),
    path("dashboard/connectwise/generate/", views.generate_connectwise_feed_view, name="connectwise_generate_feed"),
    path("dashboard/summary/draft/", views.draft_summary, name="draft_summary"),
    path("dashboard/account/<str:qb_account_id>/suggest/", views.reconcile_account_suggest, name="reconcile_account_suggest"),
    path("dashboard/account/<str:qb_account_id>/apply/", views.reconcile_account_apply, name="reconcile_account_apply"),
    path("dashboard/balance/set/", views.set_bank_balance, name="set_bank_balance"),
    path("dashboard/flag/<int:flag_id>/approve/", views.flag_approve, name="flag_approve"),
    path("dashboard/flag/<int:flag_id>/reject/", views.flag_reject, name="flag_reject"),
    path("dashboard/summary/<str:month>/review/", views.summary_review, name="summary_review"),
]
