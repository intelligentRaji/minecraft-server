#!/usr/bin/env python3
"""Reusable RCON helper for executing commands against mc-forge-server."""

from __future__ import annotations

import argparse
from pathlib import Path
import shlex
import subprocess
import sys

CONTAINER_NAME = "mc-forge-server"
DEFAULT_TIMEOUT_SECONDS = 30


def find_repo_root(start: Path) -> Path:
    """Walk upward from start to locate the repository root (containing docker-compose.yml)."""
    for candidate in (start, *start.parents):
        if (candidate / "docker-compose.yml").is_file():
            return candidate
    raise RuntimeError(f"Could not locate repository root (docker-compose.yml) above {start}")


REPO_ROOT = find_repo_root(Path(__file__).resolve().parent)


def run_rcon_batch(
    commands: list[str],
    dry_run: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Execute one or more Minecraft commands in a single rcon-cli invocation."""
    cleaned = [cmd.strip().lstrip("/") for cmd in commands if cmd.strip()]
    if not cleaned:
        raise ValueError("At least one non-empty RCON command is required.")

    full_cmd = ["docker", "exec", CONTAINER_NAME, "rcon-cli", *cleaned]
    if dry_run:
        print(f"[dry-run] {shlex.join(full_cmd)}")
        return ""

    try:
        result = subprocess.run(
            full_cmd,
            cwd=REPO_ROOT,
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except FileNotFoundError as exc:
        raise RuntimeError(f"Required executable not found: {full_cmd[0]}") from exc
    except subprocess.TimeoutExpired as exc:
        raise RuntimeError(f"RCON command timed out after {timeout}s: {shlex.join(full_cmd)}") from exc

    if result.returncode != 0:
        stderr = result.stderr.strip() or result.stdout.strip()
        raise RuntimeError(
            f"RCON failed ({shlex.join(full_cmd)}): {stderr} (is '{CONTAINER_NAME}' running?)"
        )
    return result.stdout.strip()


def run_rcon(
    command: str,
    dry_run: bool = False,
    timeout: int = DEFAULT_TIMEOUT_SECONDS,
) -> str:
    """Execute a single Minecraft command via rcon-cli."""
    return run_rcon_batch([command], dry_run=dry_run, timeout=timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Execute one or more Minecraft commands via RCON on mc-forge-server."
    )
    parser.add_argument(
        "commands",
        nargs="+",
        help="Minecraft server command(s) to run (without leading '/')",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Print the docker exec rcon-cli command without executing it",
    )
    parser.add_argument(
        "--timeout",
        type=int,
        default=DEFAULT_TIMEOUT_SECONDS,
        help=f"Command timeout in seconds (default: {DEFAULT_TIMEOUT_SECONDS})",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    try:
        output = run_rcon_batch(args.commands, dry_run=args.dry_run, timeout=args.timeout)
        if output:
            print(output)
    except (RuntimeError, ValueError) as exc:
        print(f"Error: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
