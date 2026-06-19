"""``apply_account_fix`` management command.

Apply a single reconciliation suggestion to QuickBooks by id. By default the command
prints a dry-run preview; pass ``--apply`` to execute the write.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.quickbooks import tokens as qb_tokens
from core.services.reconciliation import apply_account_reconciliation_suggestions


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

    def handle(self, *args, **options) -> None:
        month = options["month"]
        realm_id = self._resolve_realm_id(options.get("realm_id"))
        qb_account_id = options["account_id"]
        suggestion_id = options["suggestion_id"]
        apply = options["apply"]

        result = apply_account_reconciliation_suggestions(
            month=month,
            realm_id=realm_id,
            qb_account_id=qb_account_id,
            suggestion_ids=[suggestion_id],
            dry_run=not apply,
        )

        if result["dry_run"]:
            if not result["selected"]:
                raise CommandError(
                    f"Suggestion {suggestion_id!r} not found for {qb_account_id}/{month}."
                )
            suggestion = result["selected"][0]
            self.stdout.write("Preview (dry run) — pass --apply to write to QuickBooks:")
            self.stdout.write(f"  Type:        {suggestion['type']}")
            self.stdout.write(f"  Amount:      ${suggestion['amount']}")
            self.stdout.write(f"  Date:        {suggestion.get('date', '')}")
            self.stdout.write(
                f"  Description: {suggestion.get('description', '')}"
            )
            return

        if not result["success"]:
            raise CommandError(result["error"] or "Failed to apply suggestion.")

        created = result["created_objects"][0] if result["created_objects"] else {}
        self.stdout.write(
            self.style.SUCCESS(
                f"Created {created.get('object_type', 'object')} {created.get('id', '')} "
                f"for ${created.get('amount', '')}."
            )
        )
