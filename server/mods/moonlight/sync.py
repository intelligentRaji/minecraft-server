#!/usr/bin/env python3
"""One-way deterministic configuration placement for Moonlight Lib.

Places static configuration from `mods/moonlight/configs/` into `data/`:
- `config/moonlight-common.toml` -> `data/config/moonlight-common.toml`

Validates schema types, dependency invariants, runtime state isolation, and
secret guards before touching `data/`.
"""

from __future__ import annotations

import sys
from pathlib import Path, PurePosixPath

MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    DEFAULT_FORBIDDEN_SUFFIXES,
    apply_static_files,
    check_table_keys,
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MOD_DIR.parent.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

TARGET_REL_PATH = "config/moonlight-common.toml"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    TARGET_REL_PATH: ("config", "moonlight-common.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "world",
    "mods",
    "moonlight-global-datapacks",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

BOOL_GENERAL_KEYS: tuple[str, ...] = (
    "clear_dynamic_resources",
    "multi_threaded_generation",
    "extra_debug",
    "extra_children_debug",
)

EXPECTED_GENERAL_KEYS: tuple[str, ...] = (
    *BOOL_GENERAL_KEYS,
    "global_datapacks_folder",
)


def validate_moonlight_common(data: object) -> list[str]:
    """Validate schema, types, and dependency invariants for `config/moonlight-common.toml`."""
    errors = check_table_keys(data, TARGET_REL_PATH, ("general",))
    if errors or not isinstance(data, dict):
        return errors

    general = data["general"]
    errors.extend(
        check_table_keys(general, f"{TARGET_REL_PATH} [general]", EXPECTED_GENERAL_KEYS)
    )
    if not isinstance(general, dict):
        return errors

    for key in BOOL_GENERAL_KEYS:
        if key not in general:
            continue
        value = general[key]
        if not isinstance(value, bool):
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: [general].{key} must be a boolean "
                f"(got {type(value).__name__}: {value!r}) because Moonlight Lib reads "
                "each general toggle as a strict true/false ForgeConfigSpec boolean."
            )

    if "global_datapacks_folder" in general:
        folder = general["global_datapacks_folder"]
        if not isinstance(folder, str):
            errors.append(
                f"{TARGET_REL_PATH} invariant violation: [general].global_datapacks_folder "
                f"must be a string (got {type(folder).__name__}: {folder!r}) because "
                "Moonlight Lib resolves it as a folder path or empty string to disable."
            )
        elif folder != "":
            normalized = folder.replace("\\", "/")
            if folder.startswith("/") or Path(folder).is_absolute() or ".." in PurePosixPath(normalized).parts:
                errors.append(
                    f"{TARGET_REL_PATH} invariant violation: [general].global_datapacks_folder "
                    f"({folder!r}) must be a relative path without '..' or a leading '/' so "
                    "Moonlight Lib cannot escape the server data directory when loading global datapacks."
                )

    if (
        isinstance(general.get("extra_children_debug"), bool)
        and isinstance(general.get("extra_debug"), bool)
        and general["extra_children_debug"] is True
        and general["extra_debug"] is False
    ):
        errors.append(
            f"{TARGET_REL_PATH} invariant violation: [general].extra_children_debug=true "
            "requires [general].extra_debug=true because Moonlight Lib only logs "
            "BlockTypes' children into the dynamic registry dump when extra_debug is enabled."
        )

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/moonlight/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {TARGET_REL_PATH: validate_moonlight_common},
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Moonlight Lib static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "moonlight",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Moonlight Lib static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
