"""``sync_quickbooks`` management command (Prompt 3).

Pulls Purchase / Deposit / JournalEntry records from QuickBooks Online for the
configured (sandbox) realm, normalizes each into a ``Transaction``, and skips any
already present (matched on ``qb_transaction_id``). Uses the stored ``QBToken`` to
authenticate; raises ``CommandError`` when no token is stored. Retry/backoff and
mid-sync token refresh are handled by ``core.quickbooks.client`` (Prompt 5).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens


class Command(BaseCommand):
    help = (
        "Pull Purchase/Deposit/JournalEntry records from QuickBooks and normalize "
        "them into Transaction rows (idempotent on qb_transaction_id). Handles token "
        "expiry and transient API errors automatically."
    )

    def handle(self, *args, **options) -> None:
        token = qb_tokens.get_active_token()
        if token is None:
            raise CommandError(
                "No QuickBooks token is stored. Complete the OAuth flow at "
                "/quickbooks/oauth/start/ first."
            )

        self.stdout.write(self.style.NOTICE(
            f"Syncing QuickBooks realm {token.realm_id}..."
        ))
        qb = qb_client.build_quickbooks_client(token)
        result = qb_client.sync_transactions(qb, qb_token=token)

        if result.get("errors"):
            raise CommandError(
                f"Sync failed: {result.get('error_message', 'unknown error')}"
            )

        self.stdout.write(self.style.SUCCESS(
            f"Sync complete: created={result['created']} skipped={result['skipped']} "
            f"errors={result['errors']}"
        ))
        for source_type, counts in result["per_type"].items():
            self.stdout.write(
                f"  {source_type}: created={counts['created']} skipped={counts['skipped']}"
            )