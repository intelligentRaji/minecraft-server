#!/usr/bin/env python3
"""One-way deterministic configuration placement for Just Enough Items (JEI).

Places static configuration from `mods/jei/configs/` into `data/`:
- `config/jei/server/world/default/jei-server.ini` -> `data/config/jei/server/world/default/jei-server.ini`
- `world/serverconfig/jei/jei-server.ini` -> `data/world/serverconfig/jei/jei-server.ini`

Validates INI schema, cheat permission flags, cross-file consistency, runtime state
isolation, and secret guards before touching `data/`.
"""

from __future__ import annotations

import configparser
import sys
from pathlib import Path

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

DEFAULT_REL_PATH = "config/jei/server/world/default/jei-server.ini"
SERVER_REL_PATH = "world/serverconfig/jei/jei-server.ini"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    DEFAULT_REL_PATH: ("config", "jei", "server", "world", "default", "jei-server.ini"),
    SERVER_REL_PATH: ("world", "serverconfig", "jei", "jei-server.ini"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "logs",
    "mods",
    "playerdata",
    "region",
    "entities",
    "poi",
    "jei-client.ini",
    "blacklist.cfg",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

EXPECTED_SECTIONS: tuple[str, ...] = ("permissions",)
EXPECTED_PERMISSIONS_KEYS: tuple[str, ...] = (
    "enableCheatModeForOp",
    "enableCheatModeForCreative",
    "enableCheatModeForGive",
)
VALID_BOOLEAN_STRINGS: frozenset[str] = frozenset({"true", "false"})


def _check_exact_keys(
    table: object,
    label: str,
    required_keys: tuple[str, ...],
    rationale: str,
) -> list[str]:
    """Wrap `check_table_keys` with an architectural rationale for why exact keys are enforced."""
    base_errors = check_table_keys(table, label, required_keys)
    return [f"{err} ({rationale})" for err in base_errors]


def validate_jei_ini(data: object, rel_path: str) -> list[str]:
    """Validate section structure, permission keys, and strict boolean string values for a JEI server INI file."""
    errors = _check_exact_keys(
        data,
        f"{rel_path} [root]",
        EXPECTED_SECTIONS,
        "JEI server config must declare only the documented 'permissions' section so mezz_config "
        "deserializes server cheat permissions without unvalidated or rogue sections.",
    )
    if not isinstance(data, dict):
        return errors

    perms = data.get("permissions")
    if perms is None:
        return errors

    errors.extend(
        _check_exact_keys(
            perms,
            f"{rel_path} [permissions]",
            EXPECTED_PERMISSIONS_KEYS,
            "JEI server config [permissions] section must declare exactly 'enableCheatModeForOp', "
            "'enableCheatModeForCreative', and 'enableCheatModeForGive' so cheat mode access is "
            "explicitly and deterministically configured.",
        )
    )
    if not isinstance(perms, dict):
        return errors

    for key in EXPECTED_PERMISSIONS_KEYS:
        if key not in perms:
            continue
        val = perms[key]
        if not isinstance(val, str) or val not in VALID_BOOLEAN_STRINGS:
            errors.append(
                f"{rel_path} [permissions].{key} invariant violation: must be a strict boolean "
                f"string ('true' or 'false') (got {val!r}) because mezz_config parses this setting "
                "into an IConfigValue<Boolean> controlling whether JEI cheat mode is granted."
            )

    return errors


def _extract_permissions_map(raw_text: str) -> dict[str, str]:
    """Parse raw INI text and extract the [permissions] key-value pairs."""
    parser = configparser.ConfigParser()
    parser.optionxform = str
    parser.read_string(raw_text)
    if "permissions" in parser:
        return dict(parser.items("permissions"))
    return {}


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/jei/configs/` before placement."""
    loaded_bytes = validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            DEFAULT_REL_PATH: lambda d: validate_jei_ini(d, DEFAULT_REL_PATH),
            SERVER_REL_PATH: lambda d: validate_jei_ini(d, SERVER_REL_PATH),
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )

    # Consistency invariant: default template and active world serverconfig must match
    default_text = loaded_bytes[DEFAULT_REL_PATH].decode("utf-8")
    server_text = loaded_bytes[SERVER_REL_PATH].decode("utf-8")
    default_perms = _extract_permissions_map(default_text)
    server_perms = _extract_permissions_map(server_text)
    if default_perms != server_perms:
        raise ValueError(
            f"JEI server config consistency invariant violation: '{DEFAULT_REL_PATH}' "
            f"({default_perms}) and '{SERVER_REL_PATH}' ({server_perms}) have divergent "
            "[permissions] settings. Both must remain identical so default world creation "
            "and active world cheat permissions never drift."
        )

    return loaded_bytes


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated JEI static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "jei",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place JEI static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
