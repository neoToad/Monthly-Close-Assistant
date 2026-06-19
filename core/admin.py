"""Django admin registration for the core models (Prompt 2 — Postgres Schema).

All four models are registered with list displays, filters, and search fields tuned
for an internal reviewer scanning the close data.
"""
from __future__ import annotations

from django.contrib import admin

from core.models import (
    BankStatementBalance,
    BankTransaction,
    CloseSummary,
    Flag,
    QBAccount,
    QBToken,
    QuickBooksCompany,
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


@admin.register(QBToken)
class QBTokenAdmin(admin.ModelAdmin):
    """Read-only-ish view of the stored QuickBooks OAuth tokens.

    The encrypted token fields are deliberately excluded from ``list_display`` and
    ``fields`` so a reviewer never sees raw (or ciphertext) secrets in the admin.
    """
    list_display = ("realm_id", "last_refreshed", "access_token_expires_at", "updated_at")
    list_filter = ("updated_at",)
    search_fields = ("realm_id",)
    fields = ("realm_id", "last_refreshed", "access_token_expires_at",
              "refresh_token_expires_at", "created_at", "updated_at")
    readonly_fields = ("realm_id", "last_refreshed", "access_token_expires_at",
                        "refresh_token_expires_at", "created_at", "updated_at")


@admin.register(BankStatementBalance)
class BankStatementBalanceAdmin(admin.ModelAdmin):
    list_display = ("account_name", "month", "ending_balance", "source", "realm_id")
    list_filter = ("source", "month")
    search_fields = ("account_name", "qb_account_id", "realm_id")


@admin.register(QBAccount)
class QBAccountAdmin(admin.ModelAdmin):
    list_display = ("name", "account_type", "account_sub_type", "active", "realm_id")
    list_filter = ("account_type", "active")
    search_fields = ("name", "account_id", "realm_id")


@admin.register(QuickBooksCompany)
class QuickBooksCompanyAdmin(admin.ModelAdmin):
    list_display = ("realm_id", "name", "is_connected", "created_at")
    list_filter = ("is_connected", "created_at")
    search_fields = ("realm_id", "name")
    readonly_fields = ("realm_id", "created_at")