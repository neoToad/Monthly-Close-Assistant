"""Django admin registration for the core models (Prompt 2 — Postgres Schema).

All four models are registered with list displays, filters, and search fields tuned
for an internal reviewer scanning the close data.
"""
from __future__ import annotations

from django.contrib import admin

from core.models import (
    BankTransaction,
    CloseSummary,
    Flag,
    Transaction,
)


@admin.register(Transaction)
class TransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "vendor", "amount", "category", "source_type", "qb_transaction_id")
    list_filter = ("source_type", "date", "category")
    search_fields = ("vendor", "qb_transaction_id", "category", "gl_account")
    date_hierarchy = "date"


@admin.register(BankTransaction)
class BankTransactionAdmin(admin.ModelAdmin):
    list_display = ("date", "vendor", "amount", "matched_transaction_id")
    list_filter = ("date",)
    search_fields = ("vendor", "qb_transaction_id")
    date_hierarchy = "date"


@admin.register(Flag)
class FlagAdmin(admin.ModelAdmin):
    list_display = ("flag_type", "severity", "status", "transaction", "bank_transaction", "created_at")
    list_filter = ("flag_type", "severity", "status", "created_at")
    search_fields = ("reason",)


@admin.register(CloseSummary)
class CloseSummaryAdmin(admin.ModelAdmin):
    list_display = ("month", "status", "created_at")
    list_filter = ("status",)
    search_fields = ("month", "summary_text", "reviewer_notes")