"""Core data models for the Monthly Close Assistant (Prompt 2 — Postgres Schema).

The schema captures the two sides of a reconciliation (QuickBooks-sourced
``Transaction`` vs. bank-feed ``BankTransaction``), the ``Flag`` records raised by
the analysis engine, and the agent-drafted ``CloseSummary`` for human review.
"""
from __future__ import annotations

import datetime as dt

from django.core.validators import RegexValidator
from django.db import models
from django.utils import timezone


class SourceType(models.TextChoices):
    """The QuickBooks record type a Transaction was normalized from."""

    PURCHASE = "Purchase", "Purchase"
    DEPOSIT = "Deposit", "Deposit"
    JOURNAL_ENTRY = "JournalEntry", "Journal Entry"


class Transaction(models.Model):
    """A QuickBooks-sourced transaction, normalized into the internal schema.

    Pulled from Purchase, Deposit, and JournalEntry records during sync.
    ``qb_transaction_id`` is the natural key used for idempotent sync (skip-existing).
    """

    date = models.DateField(help_text="Transaction date as recorded in QuickBooks.")
    vendor = models.CharField(max_length=200, help_text="Payee / vendor name.")
    amount = models.DecimalField(
        max_digits=12, decimal_places=2, help_text="Transaction amount in USD."
    )
    category = models.CharField(
        max_length=100, blank=True, default="", help_text="Expense/income category."
    )
    gl_account = models.CharField(
        max_length=100, blank=True, default="", help_text="General ledger account."
    )
    qb_transaction_id = models.CharField(
        max_length=100,
        unique=True,
        db_index=True,
        help_text="QuickBooks transaction id; natural key for idempotent sync.",
    )
    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, help_text="QuickBooks record type."
    )

    class Meta:
        ordering = ["-date", "vendor"]

    def __str__(self) -> str:
        return f"{self.date} {self.vendor} {self.amount} ({self.source_type})"


class BankTransaction(models.Model):
    """The bank-feed side of a transaction, derived from QuickBooks data.

    Mirrors the ``Transaction`` shape and carries an optional link to the GL
    ``Transaction`` it was matched to during reconciliation (nullable because a bank
    entry may have no GL match).
    """

    date = models.DateField(help_text="Date the transaction posted to the bank.")
    vendor = models.CharField(max_length=200, blank=True, default="")
    amount = models.DecimalField(max_digits=12, decimal_places=2)
    category = models.CharField(max_length=100, blank=True, default="")
    gl_account = models.CharField(max_length=100, blank=True, default="")
    qb_transaction_id = models.CharField(
        max_length=100,
        blank=True,
        null=True,
        db_index=True,
        help_text="Originating QuickBooks id, if derived from a GL transaction.",
    )
    source_type = models.CharField(
        max_length=20, choices=SourceType.choices, blank=True, default=""
    )
    matched_transaction_id = models.ForeignKey(
        Transaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="bank_transactions",
        help_text="The GL Transaction this bank entry was matched to, if any.",
    )

    class Meta:
        ordering = ["-date", "vendor"]

    def __str__(self) -> str:
        return f"Bank {self.date} {self.vendor} {self.amount}"


class FlagType(models.TextChoices):
    """Kind of issue a Flag records."""

    RECONCILIATION = "reconciliation", "Reconciliation"
    ANOMALY = "anomaly", "Anomaly"


class Severity(models.TextChoices):
    """Rough severity for triage on the review dashboard."""

    LOW = "low", "Low"
    MEDIUM = "medium", "Medium"
    HIGH = "high", "High"


class FlagStatus(models.TextChoices):
    """Lifecycle of a Flag on the human review dashboard."""

    OPEN = "open", "Open"
    APPROVED = "approved", "Approved"
    REJECTED = "rejected", "Rejected"


class Flag(models.Model):
    """A reconciliation mismatch or anomaly raised for human review.

    Relates to either a ``Transaction`` or a ``BankTransaction`` (whichever side the
    issue is on); both are nullable because a flag may point at only one side.
    """

    flag_type = models.CharField(max_length=20, choices=FlagType.choices)
    transaction = models.ForeignKey(
        Transaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="flags",
        help_text="The GL transaction this flag concerns, if any.",
    )
    bank_transaction = models.ForeignKey(
        BankTransaction,
        null=True,
        blank=True,
        on_delete=models.SET_NULL,
        related_name="flags",
        help_text="The bank transaction this flag concerns, if any.",
    )
    reason = models.TextField(help_text="Human-readable explanation of the issue.")
    severity = models.CharField(
        max_length=10, choices=Severity.choices, default=Severity.LOW
    )
    status = models.CharField(
        max_length=10, choices=FlagStatus.choices, default=FlagStatus.OPEN
    )
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-created_at"]

    def __str__(self) -> str:
        reason_preview = (self.reason or "")[:50]
        return f"[{self.severity}] {self.flag_type}: {reason_preview}"

    def display_vendor(self) -> str:
        """Return the vendor name from whichever side the flag points to."""
        if self.transaction_id is not None and self.transaction.vendor:
            return self.transaction.vendor
        if self.bank_transaction_id is not None and self.bank_transaction.vendor:
            return self.bank_transaction.vendor
        return "—"

    def display_amount(self) -> "Decimal | None":
        """Return the amount from whichever side the flag points to."""
        if self.transaction_id is not None:
            return self.transaction.amount
        if self.bank_transaction_id is not None:
            return self.bank_transaction.amount
        return None


class CloseSummaryStatus(models.TextChoices):
    """Review state of an agent-drafted close summary."""

    DRAFT = "draft", "Draft"
    REVIEWED = "reviewed", "Reviewed"


class CloseSummary(models.Model):
    """An agent-generated monthly close draft awaiting human review.

    The agent only ever produces draft text; a human marks it reviewed (with notes).
    One summary per month (``month`` is unique).
    """

    month = models.CharField(
        max_length=7,
        unique=True,
        validators=[RegexValidator(r"^\d{4}-\d{2}$", "Month must be in YYYY-MM format.")],
        help_text="The close month in YYYY-MM format.",
    )
    summary_text = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=10,
        choices=CloseSummaryStatus.choices,
        default=CloseSummaryStatus.DRAFT,
    )
    reviewer_notes = models.TextField(blank=True, default="")
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["-month"]
        verbose_name_plural = "close summaries"

    def __str__(self) -> str:
        return f"Close summary {self.month} ({self.status})"


class QBToken(models.Model):
    """Encrypted QuickBooks OAuth tokens, one row per realm (company).

    Added in Prompt 3 so the OAuth callback and the ``sync_quickbooks`` command can
    persist access/refresh tokens at rest and reload them later. The token values
    are stored Fernet-encrypted (see ``core.quickbooks.tokens``); the model exposes
    plaintext accessors only through ``get_access_token`` / ``get_refresh_token``.
    """

    realm_id = models.CharField(
        max_length=50,
        unique=True,
        db_index=True,
        help_text="QuickBooks company/realm id (the sandbox realm for this build).",
    )
    access_token_encrypted = models.TextField(help_text="Fernet-encrypted access token.")
    refresh_token_encrypted = models.TextField(help_text="Fernet-encrypted refresh token.")
    access_token_expires_at = models.DateTimeField(
        null=True, blank=True, help_text="When the access token expires."
    )
    refresh_token_expires_at = models.DateTimeField(
        null=True, blank=True, help_text="When the (long-lived) refresh token expires."
    )
    last_refreshed = models.DateTimeField(null=True, blank=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        ordering = ["-updated_at"]

    def __str__(self) -> str:
        return f"QBToken realm={self.realm_id} (refreshed {self.last_refreshed})"

    def get_access_token(self) -> str:
        from core.quickbooks.tokens import decrypt_value

        return decrypt_value(self.access_token_encrypted)

    def get_refresh_token(self) -> str:
        from core.quickbooks.tokens import decrypt_value

        return decrypt_value(self.refresh_token_encrypted)

    def is_access_token_expired(self, buffer_minutes: Optional[int] = None) -> bool:
        """Return True when the access token is expired or within the refresh buffer.

        ``buffer_minutes`` defaults to ``QB_TOKEN_REFRESH_BUFFER_MINUTES`` from
        Django settings (Prompt 4). A token expiring inside that window is treated as
        expired so it can be refreshed before the QuickBooks API rejects it mid-sync.
        """
        if self.access_token_expires_at is None:
            return True

        if buffer_minutes is None:
            from django.conf import settings

            buffer_minutes = getattr(settings, "QB_TOKEN_REFRESH_BUFFER_MINUTES", 15)

        buffer = dt.timedelta(minutes=int(buffer_minutes))
        return self.access_token_expires_at <= timezone.now() + buffer