"""``suggest_account_fixes`` management command.

Generates AI-assisted adjusting-entry suggestions for a single account/month.
By default the command prints the proposals without touching QuickBooks; pass
``--apply`` to execute the highest-confidence suggestions.
"""
from __future__ import annotations

from django.core.management.base import BaseCommand, CommandError

from core.agents import account_reconcile as reconcile_agent
from core.quickbooks import client as qb_client
from core.quickbooks import tokens as qb_tokens
from core.services import qb_writes


class Command(BaseCommand):
    help = (
        "Generate AI-assisted reconciliation suggestions for a single "
        "QuickBooks account and month. Prints suggestions; use --apply to "
        "execute the highest-confidence suggestions in QuickBooks."
    )

    def add_arguments(self, parser) -> None:
        parser.add_argument("month", help="Month in YYYY-MM format.")
        parser.add_argument(
            "--realm-id",
            help="QuickBooks realm ID (company) to scope the suggestion to.",
        )
        parser.add_argument(
            "--account-id",
            required=True,
            help="QuickBooks account id to reconcile.",
        )
        parser.add_argument(
            "--apply",
            action="store_true",
            help="Apply the highest-confidence suggestions (high first, then medium, then low).",
        )
        parser.add_argument(
            "--confidence",
            default="",
            help="Minimum confidence to apply when --apply is set (high, medium, low).",
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

    def _select_suggestions(self, suggestions: list[dict], confidence: str) -> list[dict]:
        """Return the suggestions to apply.

        When ``confidence`` is empty, apply the highest-confidence tier that has
        any suggestions. When it is set, apply only suggestions with that exact
        confidence value.
        """
        if confidence:
            if confidence not in {"high", "medium", "low"}:
                raise CommandError("--confidence must be high, medium, or low.")
            return [s for s in suggestions if s.get("confidence") == confidence]

        for level in ("high", "medium", "low"):
            subset = [s for s in suggestions if s.get("confidence") == level]
            if subset:
                return subset
        return []

    def _apply_suggestions(
        self,
        month: str,
        realm_id: str,
        qb_account_id: str,
        suggestions: list[dict],
        account_name: str,
    ) -> None:
        """Write each selected suggestion to QuickBooks."""
        token = qb_tokens.get_active_token(realm_id=realm_id)
        if token is None:
            raise CommandError(
                "QuickBooks is not connected. Please connect QuickBooks first."
            )
        try:
            qb = qb_client.build_quickbooks_client(token)
        except Exception as exc:
            raise CommandError(f"Could not build QuickBooks client: {exc}") from exc

        created_count = 0
        for suggestion in suggestions:
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
                created_count += 1
                self.stdout.write(
                    self.style.SUCCESS(
                        f"Created {created['object_type']} {created['id']} "
                        f"for ${created['amount']}"
                    )
                )
            except Exception as exc:
                raise CommandError(
                    f"Failed to apply suggestion {suggestion.get('id')}: {exc}"
                ) from exc

        self.stdout.write(
            self.style.SUCCESS(
                f"Applied {created_count} adjustment(s) to QuickBooks for {account_name}."
            )
        )

    def handle(self, *args, **options) -> None:
        month = options["month"]
        realm_id = self._resolve_realm_id(options.get("realm_id"))
        qb_account_id = options["account_id"]
        apply = options["apply"]
        confidence = (options.get("confidence") or "").lower()

        result = reconcile_agent.suggest_account_fixes(month, realm_id, qb_account_id)
        suggestions = result["suggestions"]

        self.stdout.write(f"Account: {result['account_name']} ({qb_account_id})")
        self.stdout.write(f"Month:   {month}")
        self.stdout.write(
            f"Bank statement balance: ${result['statement_balance'] or 0}"
        )
        self.stdout.write(f"Posted GL total:        ${result['posted_total']}")
        self.stdout.write(f"Difference:             ${result['difference'] or 0}")
        self.stdout.write("")

        if not suggestions:
            self.stdout.write(self.style.WARNING("No suggestions generated."))
            return

        self.stdout.write(f"{len(suggestions)} suggestion(s):")
        for suggestion in suggestions:
            self.stdout.write(
                f"  {suggestion['id']:<10} {suggestion['type']:<16} "
                f"${suggestion['amount']:<12} {suggestion['confidence']:<7} "
                f"{suggestion.get('description', '')}"
            )

        if not apply:
            return

        to_apply = self._select_suggestions(suggestions, confidence)
        if not to_apply:
            self.stdout.write(
                self.style.WARNING(
                    "No suggestions matched the confidence threshold; nothing applied."
                )
            )
            return

        self._apply_suggestions(
            month, realm_id, qb_account_id, to_apply, result["account_name"]
        )
