"""Schema and primitive type validation helpers for mod configs."""

from __future__ import annotations

import math
from collections.abc import Iterable
from typing import TypeGuard


def is_strict_int(value: object) -> TypeGuard[int]:
    """Return True if `value` is an int and not a bool."""
    return isinstance(value, int) and not isinstance(value, bool)


def is_finite_number(value: object) -> TypeGuard[int | float]:
    """Return True if `value` is a finite int or float (and not a bool)."""
    return (
        isinstance(value, (int, float))
        and not isinstance(value, bool)
        and math.isfinite(value)
    )


def check_table_keys(
    table: object,
    label: str,
    required_keys: Iterable[str],
    optional_keys: Iterable[str] = (),
) -> list[str]:
    """Verify `table` is a dict containing all `required_keys` and no unexpected keys."""
    if not isinstance(table, dict):
        return [
            f"{label}: expected a mapping/table (got {type(table).__name__})"
        ]

    errors: list[str] = []
    required_set = set(required_keys)
    allowed_set = required_set | set(optional_keys)
    actual_set = set(table.keys())

    missing = sorted(required_set - actual_set)
    if missing:
        errors.append(f"{label}: missing required keys {missing}")

    unexpected = sorted(actual_set - allowed_set)
    if unexpected:
        errors.append(f"{label}: unexpected keys {unexpected}")

    return errors
