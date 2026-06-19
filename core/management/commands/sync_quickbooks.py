"""``sync_quickbooks`` management command (Prompt 3).

Pulls Purchase / Deposit / JournalEntry records from QuickBooks Online for the
configured (sandbox) realm, normalizes each into a ``Transaction``, and skips any
already present (matched on ``(realm_id, qb_transaction_id)``). Uses the stored
``QBToken`` to authenticate; raises ``CommandError`` when no token is stored.
Retry/backoff and mid-sync token refresh are handled by ``core.quickbooks.client``
(Prompt 5).
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.models import QuickBooksCompany
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens


class Command(BaseCommand):
    help = (
        "Pull Purchase/Deposit/JournalEntry records from QuickBooks and normalize "
        "them into Transaction rows (idempotent on realm_id + qb_transaction_id). "
        "Handles token expiry and transient API errors automatically."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm id to sync. If omitted, syncs all connected companies.",
        )

    def handle(self, *args, **options) -> None:
        realm_id = options.get("realm_id")

        if realm_id:
            tokens = [qb_tokens.get_active_token(realm_id=realm_id)]
        else:
            tokens = list(qb_tokens.get_active_tokens())

        if not tokens or all(t is None for t in tokens):
            raise CommandError(
                "No QuickBooks token is stored. Complete the OAuth flow at "
                "/quickbooks/oauth/start/ first."
            )

        total_created = total_skipped = total_errors = 0
        for token in tokens:
            if token is None:
                continue
            qb = qb_client.build_quickbooks_client(token)

            # Refresh the company display name before pulling transactions.
            name = qb_client.fetch_company_name(qb, qb_token=token)
            if name:
                QuickBooksCompany.objects.update_or_create(
                    realm_id=token.realm_id,
                    defaults={"name": name},
                )

            display = f" ({name})" if name else ""
            self.stdout.write(self.style.NOTICE(
                f"Syncing QuickBooks realm {token.realm_id}{display}..."
            ))
            result = qb_client.sync_transactions(qb, qb_token=token, realm_id=token.realm_id)

            if result.get("errors"):
                self.stdout.write(self.style.ERROR(
                    f"Sync failed for {token.realm_id}: "
                    f"{result.get('error_message', 'unknown error')}"
                ))
                total_errors += 1
                continue

            self.stdout.write(self.style.SUCCESS(
                f"Sync complete for {token.realm_id}: created={result['created']} "
                f"skipped={result['skipped']} errors={result['errors']}"
            ))
            for source_type, counts in result["per_type"].items():
                self.stdout.write(
                    f"  {source_type}: created={counts['created']} skipped={counts['skipped']}"
                )
            total_created += result["created"]
            total_skipped += result["skipped"]

        if total_errors:
            raise CommandError(
                f"Sync finished with {total_errors} error(s). "
                f"Created={total_created}, skipped={total_skipped}."
            )

        self.stdout.write(self.style.SUCCESS(
            f"All syncs complete: created={total_created} skipped={total_skipped}"
        ))
