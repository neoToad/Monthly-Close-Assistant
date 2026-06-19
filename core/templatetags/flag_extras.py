"""Small template filters used by the ledger dashboard."""
from __future__ import annotations

from django import template

from core.models import FlagStatus, FlagType

register = template.Library()


@register.filter(name="status_dot_class")
def status_dot_class(status: str) -> str:
    """Map a FlagStatus value to the ledger dot color class.

    Open flags use the amber ``flag`` dot; approved/confirmed states use the
    green ``confirmed`` dot; rejected states use the brick-red ``rejected`` dot.
    """
    mapping = {
        FlagStatus.OPEN: "flag",
        FlagStatus.APPROVED: "confirmed",
        FlagStatus.REJECTED: "rejected",
    }
    return mapping.get(status, "flag")


@register.filter(name="flag_type_class")
def flag_type_class(flag_type: str) -> str:
    """Map a FlagType value to a CSS class for visual distinction.

    Balance-reconciliation flags are high-level account controls, so they get a
    distinctive ``balance`` class that the ledger can style prominently.
    """
    return "balance" if flag_type == FlagType.BALANCE_RECONCILIATION else ""


@register.filter(name="flag_type_label")
def flag_type_label(flag_type: str) -> str:
    """Return a short human-readable label for a flag type."""
    if flag_type == FlagType.BALANCE_RECONCILIATION:
        return "Balance"
    return ""
