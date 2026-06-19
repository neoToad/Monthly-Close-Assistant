"""``apply_account_fix`` management command.

Apply a single reconciliation suggestion to QuickBooks by id.  By default the
command prints a dry-run preview; pass ``--apply`` to execute the write.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.agent import reconcile as reconcile_agent
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens
from core.quickbooks import writes as qb_writes


class Command(BaseCommand):
    help = (
        "Apply a single reconciliation suggestion to QuickBooks. "
        "By default prints a preview; pass --apply to execute the write."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm ID (company) to scope the fix to.",
        )
        parser.add_argument(
            "--account-id",
            required=True,
            help="QuickBooks account id the suggestion belongs to.",
        )
        parser.add_argument(
            "--suggestion-id",
            required=True,
            help="Id of the suggestion to apply.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Confirm and apply the suggestion to QuickBooks.",
        )

    def _resolve_realm_id(self, realm_id: str | None) -> str:
        if realm_id:
            return realm_id
        token = qb_tokens.get_active_token()
        if token:
            return token.realm_id
        raise CommandError(
            "--realm-id is required when no QuickBooks token is stored."
        )

    def _lookup_suggestion(
        self, result: dict, suggestion_id: str, qb_account_id: str, month: str
    ) -> dict:
        for suggestion in result["suggestions"]:
            if suggestion.get("id") == suggestion_id:
                return suggestion
        raise CommandError(
            f"Suggestion {suggestion_id!r} not found for {qb_account_id}/{month}."
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]
        realm_id = self._resolve_realm_id(options.get("realm_id"))
        qb_account_id = options["account_id"]
        suggestion_id = options["suggestion_id"]
        apply = options["apply"]

        result = reconcile_agent.suggest_account_fixes(month, realm_id, qb_account_id)
        suggestion = self._lookup_suggestion(
            result, suggestion_id, qb_account_id, month
        )

        if not apply:
            self.stdout.write("Preview (dry run) — pass --apply to write to QuickBooks:")
            self.stdout.write(f"  Type:        {suggestion['type']}")
            self.stdout.write(f"  Amount:      ${suggestion['amount']}")
            self.stdout.write(f"  Date:        {suggestion.get('date', '')}")
            self.stdout.write(
                f"  Description: {suggestion.get('description', '')}"
            )
            return

        token = qb_tokens.get_active_token(realm_id=realm_id)
        if token is None:
            raise CommandError(
                "QuickBooks is not connected. Please connect QuickBooks first."
            )
        try:
            qb = qb_client.build_quickbooks_client(token)
        except Exception as exc:
            raise CommandError(f"Could not build QuickBooks client: {exc}") from exc

        try:
            created = qb_writes.apply_suggestion(
                qb,
                suggestion,
                realm_id=realm_id,
                private_note=(
                    f"AI-assisted reconciliation for {month} — "
                    f"{suggestion.get('description', '')}"
                ),
            )
        except Exception as exc:
            raise CommandError(f"Failed to apply suggestion: {exc}") from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created['object_type']} {created['id']} "
                f"for ${created['amount']}."
            )
        )
