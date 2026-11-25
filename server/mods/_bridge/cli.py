"""Standard CLI runner for `mods/<slug>/sync.py` scripts."""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable


def run_sync_cli[T](
    slug: str,
    validate_fn: Callable[[], T],
    apply_fn: Callable[[T, bool], tuple[int, int]],
    argv: list[str] | None = None,
    description: str | None = None,
) -> int:
    """Standard CLI runner for `mods/<slug>/sync.py` scripts."""
    parser = argparse.ArgumentParser(
        description=description or f"Synchronize {slug} static configurations into data/."
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Validate and preview changes without modifying files in data/.",
    )
    args = parser.parse_args(argv)

    try:
        validated = validate_fn()
    except (RuntimeError, OSError, ValueError) as exc:
        print(f"[{slug}/sync.py] ERROR: {exc}", file=sys.stderr)
        return 1

    changed, unchanged = apply_fn(validated, args.dry_run)
    total = changed + unchanged
    mode = "DRY-RUN" if args.dry_run else "APPLIED"
    print(
        f"[{slug}/sync.py] {mode}: {changed} changed, {unchanged} unchanged "
        f"(total {total} files verified)."
    )
    return 0
