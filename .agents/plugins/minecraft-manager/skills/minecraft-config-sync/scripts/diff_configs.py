#!/usr/bin/env python3
"""Show unified diff between server-config/ and data/ for allowlisted paths."""

from __future__ import annotations

import argparse
import difflib
import sys

from config_utils import DATA_DIR, SERVER_CONFIG_DIR, collect_files, sha256_file


def diff_configs(*, exit_code: bool = False) -> int:
    """Print unified diff between server-config/ and data/ for allowlisted paths."""
    repo_files = collect_files(SERVER_CONFIG_DIR, allowlist_only=True, exclude_lp_snapshot=True)
    data_files = collect_files(DATA_DIR, allowlist_only=True, exclude_lp_snapshot=True)
    all_paths = sorted(set(repo_files) | set(data_files))

    has_diff = False
    had_error = False
    for rel_posix in all_paths:
        repo_path = repo_files.get(rel_posix)
        data_path = data_files.get(rel_posix)

        if repo_path and data_path:
            try:
                if sha256_file(repo_path) == sha256_file(data_path):
                    continue
            except OSError as exc:
                print(f"ERROR: Could not read {rel_posix}: {exc}", file=sys.stderr)
                had_error = True
                continue

        try:
            repo_lines = (
                repo_path.read_text(encoding="utf-8").splitlines(keepends=True)
                if repo_path
                else []
            )
            data_lines = (
                data_path.read_text(encoding="utf-8").splitlines(keepends=True)
                if data_path
                else []
            )
        except UnicodeDecodeError as exc:
            print(f"WARNING: Non-UTF-8 file differs: {rel_posix} ({exc})", file=sys.stderr)
            has_diff = True
            continue
        except OSError as exc:
            print(f"ERROR: Could not read {rel_posix}: {exc}", file=sys.stderr)
            had_error = True
            continue

        diff = list(
            difflib.unified_diff(
                repo_lines,
                data_lines,
                fromfile=f"server-config/{rel_posix}",
                tofile=f"data/{rel_posix}",
            )
        )
        if diff:
            has_diff = True
            sys.stdout.writelines(diff)
            if not diff[-1].endswith("\n"):
                print()

    if had_error:
        return 1
    if not has_diff:
        print("No differences found between server-config/ and data/.")
        return 0
    return 1 if exit_code else 0


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="Show unified diff between server-config/ and data/ for allowlisted configs."
    )
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help="Exit with code 1 if differences are found.",
    )
    args = parser.parse_args(argv)
    return diff_configs(exit_code=args.exit_code)


if __name__ == "__main__":
    raise SystemExit(main())
