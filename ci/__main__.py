"""CLI entry point for CI/CD workflow commands (`python3 -m ci <command>`)."""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from .artifact_reuse import build_metadata, collect_subtrees, resolve_ci_e2e
from .client_build import (
    build_windows_installer,
    exclude_windows_defender_paths,
    sync_client_version,
)
from .github_env import GitHubContext, write_github_outputs
from .release_version import read_client_version, resolve_release_plan


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="python3 -m ci", description="ModSync CI/CD helpers.")
    subparsers = parser.add_subparsers(dest="command", required=True)

    subparsers.add_parser("resolve-e2e", help="Decide whether CI must run client-e2e.")
    subparsers.add_parser("prepare-release", help="Resolve release version, tag, and artifact reuse.")
    subparsers.add_parser("win-defender-exclude", help="Add Windows Defender exclusions on CI runners.")

    sync_cmd = subparsers.add_parser("sync-version", help="Sync client __init__.py __version__.")
    sync_cmd.add_argument("--version", required=True)

    inst_cmd = subparsers.add_parser("win-build-installer", help="Build ModSync-Setup.exe via Inno Setup.")
    inst_cmd.add_argument("--version", required=True)

    meta_cmd = subparsers.add_parser("write-meta", help="Write build-meta.json for artifact reuse.")
    meta_cmd.add_argument("--output", required=True, type=Path)
    meta_cmd.add_argument("--version", default="")
    meta_cmd.add_argument("--source-repo", default="")
    meta_cmd.add_argument("--head-sha", default="")
    meta_cmd.add_argument("--event", default="")

    args = parser.parse_args(argv)
    ctx = GitHubContext.from_env()

    if args.command == "resolve-e2e":
        app_version = read_client_version()
        run_e2e, exit_code = resolve_ci_e2e(
            event=ctx.event_name,
            head_sha=ctx.pr_head_sha,
            head_repo=ctx.pr_head_repo,
            base_repo=ctx.repository,
            app_version=app_version,
            base_ref=ctx.base_ref,
            before_sha=ctx.before_sha,
        )
        write_github_outputs(
            ctx.output_path,
            {
                "run_e2e": "true" if run_e2e else "false",
                "app_version": app_version,
            },
        )
        return exit_code

    if args.command == "prepare-release":
        plan = resolve_release_plan(ctx)
        write_github_outputs(ctx.output_path, plan.to_outputs())
        return 0

    if args.command == "write-meta":
        payload = build_metadata(
            version=args.version or read_client_version(),
            subtrees=collect_subtrees("HEAD"),
            source_repo=args.source_repo or ctx.pr_head_repo or ctx.repository,
            head_sha=args.head_sha or ctx.pr_head_sha or ctx.sha,
            event=args.event or ctx.event_name,
        )
        args.output.parent.mkdir(parents=True, exist_ok=True)
        args.output.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        return 0

    if args.command == "sync-version":
        sync_client_version(args.version)
        return 0

    if args.command == "win-defender-exclude":
        exclude_windows_defender_paths()
        return 0

    if args.command == "win-build-installer":
        build_windows_installer(args.version)
        return 0

    return 1


if __name__ == "__main__":
    sys.exit(main())
