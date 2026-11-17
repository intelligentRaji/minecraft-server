"""Shared non-AI Mod Bridge services for `mods/<slug>/sync.py` scripts.

Organized by domain:
- `secrets`: secret pattern & credential key scanning
- `schema`: primitive type & table-key validation helpers
- `files`: forbidden entry guards, SHA-256 hashing, and atomic file placement
- `validation`: pre-flight static config directory validation pipeline
- `cli`: standard `--dry-run` / apply CLI runner
"""

from __future__ import annotations

from .cli import run_sync_cli
from .files import (
    DEFAULT_FORBIDDEN_SUFFIXES,
    apply_static_files,
    atomic_write_bytes,
    check_forbidden_entries,
    collect_config_files,
    sha256_bytes,
    sync_static_file,
)
from .schema import check_table_keys, is_finite_number, is_strict_int
from .secrets import (
    SECRET_KEY_NAMES,
    SECRET_PATTERNS,
    scan_mapping_for_secrets,
    scan_text_for_secrets,
)
from .validation import validate_static_configs

__all__ = [
    "DEFAULT_FORBIDDEN_SUFFIXES",
    "SECRET_KEY_NAMES",
    "SECRET_PATTERNS",
    "apply_static_files",
    "atomic_write_bytes",
    "check_forbidden_entries",
    "check_table_keys",
    "collect_config_files",
    "is_finite_number",
    "is_strict_int",
    "run_sync_cli",
    "scan_mapping_for_secrets",
    "scan_text_for_secrets",
    "sha256_bytes",
    "sync_static_file",
    "validate_static_configs",
]
