#!/usr/bin/env python3
"""One-way deterministic configuration placement & block-level merge for ChickenChunks.

Places static configurations from `mods/chickenchunks/configs/ChickenChunks.cfg` into
`data/config/ChickenChunks.cfg`:
- Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
- Atomically block-merges `ChickenChunks.cfg` so live per-player UUID restrictions inside
  `"playerRestrictions" { ... }` in `data/config/ChickenChunks.cfg` are never overwritten.
- Never reads, copies, or modifies excluded runtime chunkloader state (`world/chickenchunks/`,
  `loginTimes.dat`, `.dat`, `.db`, `.sqlite`, `.jar`, `.log`, `.bak`, `.tmp`, `.lock`).
"""

from __future__ import annotations

import re
import sys
from pathlib import Path
from typing import NamedTuple

# Deterministic zero-walk path resolution (mods/chickenchunks/sync.py -> repo root)
MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    DEFAULT_FORBIDDEN_SUFFIXES,
    atomic_write_bytes,
    check_forbidden_entries,
    collect_config_files,
    run_sync_cli,
    scan_text_for_secrets,
    sha256_bytes,
)

REPO_ROOT = MODS_DIR.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"
TARGET_DIR = DATA_DIR / "config"

STATIC_FILES: tuple[str, ...] = ("ChickenChunks.cfg",)
RUNTIME_BLOCK_NAME = "playerRestrictions"
DEFAULT_PLAYER_RESTRICTIONS_COMMENT = (
    "# Specifies restrictions for each player, Use /chickenchunks instead."
)
DEFAULT_PLAYER_RESTRICTIONS_SECTION = (
    f"{DEFAULT_PLAYER_RESTRICTIONS_COMMENT}\n"
    '"playerRestrictions" {\n'
    "}"
)

MAX_OFFLINE_TIMEOUT_MINUTES = 60
MAX_TOTAL_ALLOWED_CHUNKS = 25
MAX_CHUNKS_PER_LOADER = 25

STATIC_KEY_SPECS: dict[str, tuple[str, str]] = {
    "opsBypassRestrictions": ("B", "bool"),
    "opsAccessAllLoaders": ("B", "bool"),
    "allowOffline": ("B", "bool"),
    "offlineTimeout": ("I", "non_neg_int"),
    "totalAllowedChunks": ("I", "non_neg_int"),
    "chunksPerLoader": ("I", "non_neg_int"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "chickenchunks",
    "world",
    "loginTimes.dat",
    "data",
    "libs",
    "logs",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = (*DEFAULT_FORBIDDEN_SUFFIXES, ".dat")

BLOCK_HEADER_RE = re.compile(
    r'^(?:"([^"\\]*(?:\\.[^"\\]*)*)"|([A-Za-z0-9_.-]+))\s*\{'
)
TYPED_ENTRY_RE = re.compile(
    r'^([A-Za-z]+):(?:"([^"\\]*(?:\\.[^"\\]*)*)"|([A-Za-z0-9_.-]+))\s*=\s*(.*)$'
)
UNTYPED_ENTRY_RE = re.compile(
    r'^(?:"([^"\\]*(?:\\.[^"\\]*)*)"|([A-Za-z0-9_.-]+))\s*=\s*(.*)$'
)


class CfgEntry(NamedTuple):
    """Single top-level key/value entry in a CodeChickenLib `.cfg` file."""

    type_prefix: str | None
    key: str
    value: str
    line_number: int


class CfgBlock(NamedTuple):
    """Top-level named `{ ... }` block in a CodeChickenLib `.cfg` file."""

    name: str
    start_line: int
    end_line: int


class ParsedCfg(NamedTuple):
    """Parsed top-level entries, blocks, and syntax errors from a CodeChickenLib `.cfg` file."""

    entries: list[CfgEntry]
    blocks: list[CfgBlock]
    errors: list[str]


def _find_block_end(lines: list[str], start_line: int, open_col: int) -> tuple[int, str] | None:
    """Find the matching closing `}` line index for a block whose `{` is at `(start_line, open_col)`."""
    depth = 0
    in_quotes = False
    escaped = False

    for line_idx in range(start_line, len(lines)):
        line = lines[line_idx]
        if line_idx > start_line and not in_quotes and line.lstrip().startswith("#"):
            continue

        col = open_col if line_idx == start_line else 0
        while col < len(line):
            ch = line[col]
            if escaped:
                escaped = False
            elif ch == "\\" and in_quotes:
                escaped = True
            elif ch == '"':
                in_quotes = not in_quotes
            elif not in_quotes:
                if ch == "{":
                    depth += 1
                elif ch == "}":
                    depth -= 1
                    if depth == 0:
                        return line_idx, line[col + 1 :].strip()
            col += 1

    return None


def parse_codechicken_cfg(raw_text: str, rel: str = "ChickenChunks.cfg") -> ParsedCfg:
    """Parse top-level entries and `{ ... }` blocks in CodeChickenLib `.cfg` format."""
    lines = raw_text.splitlines()
    entries: list[CfgEntry] = []
    blocks: list[CfgBlock] = []
    errors: list[str] = []

    idx = 0
    while idx < len(lines):
        stripped = lines[idx].strip()
        if not stripped or stripped.startswith("#"):
            idx += 1
            continue

        block_match = BLOCK_HEADER_RE.match(stripped)
        if block_match:
            block_name = block_match.group(1) if block_match.group(1) is not None else block_match.group(2)
            open_col = lines[idx].find("{")
            block_end = _find_block_end(lines, idx, open_col)
            if block_end is None:
                errors.append(
                    f"{rel}: line {idx + 1}: unclosed block '{block_name}' "
                    "(every CodeChickenLib '{' block must have a matching '}')"
                )
                break
            end_line, trailing = block_end
            if trailing and not trailing.startswith("#"):
                errors.append(
                    f"{rel}: line {end_line + 1}: unexpected trailing content {trailing!r} after closing '}}'"
                )
            blocks.append(CfgBlock(name=block_name, start_line=idx, end_line=end_line))
            idx = end_line + 1
            continue

        typed_match = TYPED_ENTRY_RE.match(stripped)
        if typed_match:
            type_prefix = typed_match.group(1)
            key = typed_match.group(2) if typed_match.group(2) is not None else typed_match.group(3)
            value = typed_match.group(4).strip()
            entries.append(CfgEntry(type_prefix=type_prefix, key=key, value=value, line_number=idx + 1))
            idx += 1
            continue

        untyped_match = UNTYPED_ENTRY_RE.match(stripped)
        if untyped_match:
            key = untyped_match.group(1) if untyped_match.group(1) is not None else untyped_match.group(2)
            value = untyped_match.group(3).strip()
            entries.append(CfgEntry(type_prefix=None, key=key, value=value, line_number=idx + 1))
            idx += 1
            continue

        errors.append(f"{rel}: line {idx + 1}: unrecognized CodeChickenLib config syntax {stripped!r}")
        idx += 1

    return ParsedCfg(entries=entries, blocks=blocks, errors=errors)


def _validate_static_entries(parsed: ParsedCfg, rel: str) -> list[str]:
    """Validate static keys, CodeChickenLib type prefixes, and runtime isolation invariants."""
    errors: list[str] = list(parsed.errors)

    runtime_isolation_msg = (
        f"{rel} state isolation violation: '{RUNTIME_BLOCK_NAME}' must not exist in repo configs/ "
        "because per-player UUID chunkloading restrictions managed live via /chickenchunks are server "
        "runtime state in server/data/config/ChickenChunks.cfg that sync.py preserves via block-level merge."
    )

    for block in parsed.blocks:
        if block.name == RUNTIME_BLOCK_NAME:
            errors.append(runtime_isolation_msg)
        else:
            errors.append(
                f"{rel} schema violation: unexpected block '{block.name}' in repo configs/ "
                "(only the 6 top-level administrator keys belong in static configs/ChickenChunks.cfg)"
            )

    seen_keys: dict[str, CfgEntry] = {}
    for entry in parsed.entries:
        if entry.key == RUNTIME_BLOCK_NAME:
            errors.append(runtime_isolation_msg)
            continue
        if entry.key not in STATIC_KEY_SPECS:
            errors.append(
                f"{rel} schema violation: unexpected key '{entry.key}' at line {entry.line_number} "
                f"(allowed static keys: {', '.join(STATIC_KEY_SPECS)})"
            )
            continue
        if entry.key in seen_keys:
            errors.append(
                f"{rel} schema violation: duplicate key '{entry.key}' at line {entry.line_number} "
                f"(already defined at line {seen_keys[entry.key].line_number})"
            )
            continue
        seen_keys[entry.key] = entry

    for key, (expected_prefix, kind) in STATIC_KEY_SPECS.items():
        entry = seen_keys.get(key)
        if entry is None:
            errors.append(
                f"{rel} schema violation: missing required static administrator key '{key}' "
                "(all 6 ChickenChunks chunkloading policy keys must be explicitly declared in configs/)"
            )
            continue

        if entry.type_prefix != expected_prefix:
            errors.append(
                f"{rel} type violation: '{key}' must use CodeChickenLib type prefix '{expected_prefix}:' "
                f"(got {entry.type_prefix!r}) so CodeChickenLib deserializes the setting cleanly on startup."
            )
            continue

        if kind == "bool" and entry.value not in {"true", "false"}:
            errors.append(
                f"{rel} value violation: boolean key '{key}' must be 'true' or 'false' "
                f"(got {entry.value!r}) so ChickenChunks chunkloading policy parses deterministically."
            )
            continue
        if kind == "non_neg_int" and (not re.fullmatch(r"-?\d+", entry.value) or int(entry.value) < 0):
            errors.append(
                f"{rel} value violation: integer key '{key}' must be a non-negative integer >= 0 "
                f"(got {entry.value!r}) so chunkloading limits and logout timeouts remain well-defined."
            )
            continue

        if key == "opsBypassRestrictions" and entry.value != "false":
            errors.append(
                f"{rel} invariant violation: opsBypassRestrictions must be 'false' "
                f"(got {entry.value!r}) so OP players remain subject to the server's chunkloading caps."
            )
        elif key == "allowOffline" and entry.value != "false":
            errors.append(
                f"{rel} invariant violation: allowOffline must be 'false' "
                f"(got {entry.value!r}) so chunkloaders unload when their owner is offline to protect server TPS/RAM."
            )
        elif key == "offlineTimeout" and int(entry.value) > MAX_OFFLINE_TIMEOUT_MINUTES:
            errors.append(
                f"{rel} invariant violation: offlineTimeout must be in 0..{MAX_OFFLINE_TIMEOUT_MINUTES} minutes "
                f"(got {entry.value!r}) to prevent excessive post-logout chunk retention."
            )
        elif key == "totalAllowedChunks":
            total_chunks = int(entry.value)
            if total_chunks < 1 or total_chunks > MAX_TOTAL_ALLOWED_CHUNKS:
                errors.append(
                    f"{rel} invariant violation: totalAllowedChunks must be in 1..{MAX_TOTAL_ALLOWED_CHUNKS} "
                    f"(got {entry.value!r}) to cap per-player chunkloading within the 6G server budget."
                )
        elif key == "chunksPerLoader":
            per_loader = int(entry.value)
            if per_loader < 1 or per_loader > MAX_CHUNKS_PER_LOADER:
                errors.append(
                    f"{rel} invariant violation: chunksPerLoader must be in 1..{MAX_CHUNKS_PER_LOADER} "
                    f"(got {entry.value!r}) to cap each ChunkLoader at a 5x5 area (25 chunks)."
                )

    total_entry = seen_keys.get("totalAllowedChunks")
    loader_entry = seen_keys.get("chunksPerLoader")
    if (
        total_entry is not None
        and loader_entry is not None
        and total_entry.type_prefix == "I"
        and loader_entry.type_prefix == "I"
        and re.fullmatch(r"\d+", total_entry.value)
        and re.fullmatch(r"\d+", loader_entry.value)
        and int(loader_entry.value) > int(total_entry.value)
    ):
        errors.append(
            f"{rel} invariant violation: chunksPerLoader ({loader_entry.value}) must not exceed "
            f"totalAllowedChunks ({total_entry.value}) so a single loader fits within a player's chunk quota."
        )

    return errors


def validate_configs() -> dict[str, str]:
    """Validate `mods/chickenchunks/configs/` before placing `ChickenChunks.cfg` into `data/`."""
    if not CONFIGS_DIR.is_dir():
        raise RuntimeError(f"Missing configs directory: {CONFIGS_DIR}")

    errors = check_forbidden_entries(
        CONFIGS_DIR,
        FORBIDDEN_NAMES,
        FORBIDDEN_SUFFIXES,
        suffix_label="runtime/archive",
    )
    config_files, collect_errors = collect_config_files(CONFIGS_DIR)
    errors.extend(collect_errors)

    expected_files = set(STATIC_FILES)
    actual_files = set(config_files.keys())

    missing = sorted(expected_files - actual_files)
    unexpected = sorted(actual_files - expected_files)
    if missing:
        errors.append(f"Missing expected config files in configs/: {', '.join(missing)}")
    if unexpected:
        errors.append(
            f"Unexpected files in configs/: {', '.join(unexpected)} "
            "(only static ChickenChunks.cfg may live in server/mods/chickenchunks/configs/; "
            "runtime world/player chunkloader state belongs exclusively in server/data/)"
        )

    loaded_texts: dict[str, str] = {}
    if "ChickenChunks.cfg" in config_files:
        rel = "ChickenChunks.cfg"
        try:
            raw_text = config_files[rel].read_text(encoding="utf-8")
        except UnicodeDecodeError as exc:
            errors.append(f"{rel}: invalid UTF-8 ({exc})")
        else:
            loaded_texts[rel] = raw_text
            errors.extend(scan_text_for_secrets(raw_text, rel))
            parsed = parse_codechicken_cfg(raw_text, rel)
            errors.extend(_validate_static_entries(parsed, rel))

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return loaded_texts


def extract_player_restrictions_section(raw_text: str, source_label: str) -> str | None:
    """Extract live `"playerRestrictions" { ... }` block (with attached comment) from target config."""
    lines = raw_text.splitlines()
    parsed = parse_codechicken_cfg(raw_text, source_label)
    for err in parsed.errors:
        if f"unclosed block '{RUNTIME_BLOCK_NAME}'" in err:
            raise ValueError(
                f"{source_label} contains an unclosed '{RUNTIME_BLOCK_NAME}' block; "
                "refusing to overwrite potentially corrupt live player restriction state."
            )

    matching_blocks = [block for block in parsed.blocks if block.name == RUNTIME_BLOCK_NAME]
    if not matching_blocks:
        return None

    target_block = matching_blocks[0]
    comment_start = target_block.start_line
    while comment_start > 0 and lines[comment_start - 1].lstrip().startswith("#"):
        comment_start -= 1

    block_lines = lines[target_block.start_line : target_block.end_line + 1]
    if comment_start < target_block.start_line:
        section_lines = lines[comment_start : target_block.end_line + 1]
    else:
        section_lines = [DEFAULT_PLAYER_RESTRICTIONS_COMMENT, *block_lines]

    return "\n".join(section_lines)


def sync_chickenchunks_cfg(static_text: str, dry_run: bool) -> bool:
    """Atomically block-merge static settings with live `"playerRestrictions"` in `TARGET_DIR`."""
    dst_path = TARGET_DIR / "ChickenChunks.cfg"
    existing_bytes: bytes | None = None
    trailing_newline = True
    player_restrictions_section: str | None = None

    if dst_path.exists():
        existing_bytes = dst_path.read_bytes()
        trailing_newline = existing_bytes.endswith(b"\n")
        existing_text = existing_bytes.decode("utf-8")
        player_restrictions_section = extract_player_restrictions_section(
            existing_text,
            str(dst_path),
        )

    if player_restrictions_section is None:
        player_restrictions_section = DEFAULT_PLAYER_RESTRICTIONS_SECTION

    merged_text = (
        static_text.rstrip("\r\n")
        + "\n\n"
        + player_restrictions_section.strip("\r\n")
    )
    if trailing_newline:
        merged_text += "\n"
    new_bytes = merged_text.encode("utf-8")

    if existing_bytes is not None and sha256_bytes(existing_bytes) == sha256_bytes(new_bytes):
        return False

    action = "Would block-merge (mixed)" if dry_run else "Block-merged (mixed)"
    print(f"  [{action}] ChickenChunks.cfg (preserved runtime '{RUNTIME_BLOCK_NAME}')")
    if not dry_run:
        atomic_write_bytes(dst_path, new_bytes)
    return True


def apply_configs(loaded_texts: dict[str, str], dry_run: bool) -> tuple[int, int]:
    """Place validated ChickenChunks static config into `TARGET_DIR` via block-level merge."""
    if sync_chickenchunks_cfg(loaded_texts["ChickenChunks.cfg"], dry_run=dry_run):
        return 1, 0
    return 0, 1


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "chickenchunks",
        validate_configs,
        apply_configs,
        argv=argv,
        description=(
            "Validate and atomically block-merge ChickenChunks static config "
            "into data/config/ChickenChunks.cfg."
        ),
    )


if __name__ == "__main__":
    sys.exit(main())
