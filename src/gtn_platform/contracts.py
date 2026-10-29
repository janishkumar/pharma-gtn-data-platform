"""Raw-file contracts: fail the refresh loudly when CMS changes a file layout."""

from __future__ import annotations

from .sources import normalise_column


class ContractError(Exception):
    pass


def check_header(columns: list[str], expected: tuple[str, ...], source: str) -> list[str]:
    """Return the normalised header, or raise if any expected column is missing.

    Extra columns are tolerated (CMS adds fields over time) but reported in the error text
    when something is also missing, since that usually means a rename.
    """
    normalised = [normalise_column(c) for c in columns]
    missing = [c for c in expected if c not in normalised]
    if missing:
        unexpected = [c for c in normalised if c not in expected]
        raise ContractError(f"{source}: missing={missing} unexpected={unexpected}")
    return normalised
