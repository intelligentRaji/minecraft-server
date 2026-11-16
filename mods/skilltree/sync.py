#!/usr/bin/env python3
"""One-way deterministic configuration placement for Passive Skill Tree.

Places static configurations from `mods/skilltree/configs/` into `data/`:
- `skilltree-common.toml` -> `data/config/skilltree-common.toml`
- `skilltree-server.toml` -> `data/world/serverconfig/skilltree-server.toml`

Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
Never reads, copies, or modifies excluded world/player runtime directories (`data/world/playerdata/`,
`data/world/` level/region data, `data/logs/`, `data/mods/`).
"""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge import (  # noqa: E402
    DEFAULT_FORBIDDEN_SUFFIXES,
    apply_static_files,
    is_finite_number as _is_finite_number,
    is_strict_int,
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MODS_DIR.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    "skilltree-common.toml": ("config", "skilltree-common.toml"),
    "skilltree-server.toml": ("world", "serverconfig", "skilltree-server.toml"),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "world",
    "playerdata",
    "logs",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES

EQUIPMENT_SOCKET_KEYS: tuple[str, ...] = (
    "Default Helmets Sockets",
    "Default Chestplates Sockets",
    "Default Leggings Sockets",
    "Default Boots Sockets",
    "Default Weapons Sockets",
    "Default Shields Sockets",
    "Default Rings Sockets",
    "Default Necklaces Sockets",
)


def _require_section(
    filename: str, data: dict[str, Any], section: str, errors: list[str]
) -> dict[str, Any] | None:
    """Return `data[section]` if it is a dict, otherwise record an invariant error."""
    value = data.get(section)
    if not isinstance(value, dict):
        errors.append(
            f"{filename} invariant violation: [{section}] table must be present "
            f"(got {type(value).__name__}) so Forge/Passive Skill Tree can load all required server settings."
        )
        return None
    return value


def _validate_skill_points(
    filename: str, data: dict[str, Any], *, max_points_upper: int | None
) -> list[str]:
    """Validate the `["Skill Points"]` section shared by common and server TOML files."""
    errors: list[str] = []
    section = _require_section(filename, data, "Skill Points", errors)
    if section is None:
        return errors

    max_points = section.get("Maximum skill points")
    if max_points_upper is not None:
        max_points_valid = is_strict_int(max_points) and 1 <= max_points <= max_points_upper
        if not max_points_valid:
            errors.append(
                f'{filename} invariant violation: ["Skill Points"]."Maximum skill points" '
                f"must be an integer in 1..{max_points_upper} (got {max_points!r}) to stay within "
                "Forge's common config range and keep player skill progression bounded."
            )
    else:
        max_points_valid = is_strict_int(max_points) and max_points > 1
        if not max_points_valid:
            errors.append(
                f'{filename} invariant violation: ["Skill Points"]."Maximum skill points" '
                f"must be an integer > 1 (got {max_points!r}) as required by Forge's server config range "
                "for valid skill point scaling."
            )

    for cost_key in ("First skill point cost", "Last skill point cost"):
        cost_val = section.get(cost_key)
        if not is_strict_int(cost_val) or cost_val <= 0:
            errors.append(
                f'{filename} invariant violation: ["Skill Points"]."{cost_key}" '
                f"must be an integer > 0 (got {cost_val!r}) so skill point experience costs remain "
                "strictly positive and non-exploitable."
            )

    for bool_key, rationale in (
        (
            "Use skill points costs array",
            "deterministically choose between formula scaling and the explicit Levelup costs array",
        ),
        (
            "Show chat messages",
            "control skill point gain chat notifications for players",
        ),
        (
            "Enable exprerience exchange for skill points",
            "control whether players can exchange XP for skill points",
        ),
    ):
        val = section.get(bool_key)
        if not isinstance(val, bool):
            errors.append(
                f'{filename} invariant violation: ["Skill Points"]."{bool_key}" '
                f"must be a boolean (got {val!r}) to {rationale}."
            )

    levelup_costs = section.get("Levelup costs")
    if not isinstance(levelup_costs, list):
        errors.append(
            f'{filename} invariant violation: ["Skill Points"]."Levelup costs" '
            f"must be a list of integers > 0 (got {type(levelup_costs).__name__}) so every skill level "
            "has a defined positive experience cost."
        )
    else:
        invalid_items = [
            (idx, item)
            for idx, item in enumerate(levelup_costs)
            if not is_strict_int(item) or item <= 0
        ]
        if invalid_items:
            idx, bad_val = invalid_items[0]
            errors.append(
                f'{filename} invariant violation: ["Skill Points"]."Levelup costs"[{idx}] '
                f"must be an integer > 0 (got {bad_val!r}) so no skill point levelup is free or negative."
            )
        if max_points_valid and len(levelup_costs) != max_points:
            errors.append(
                f'{filename} invariant violation: ["Skill Points"]."Levelup costs" length '
                f"({len(levelup_costs)}) must equal \"Maximum skill points\" ({max_points}) "
                "because Passive Skill Tree indexes one cost entry per skill point."
            )

    return errors


def _validate_amnesia_scroll(filename: str, data: dict[str, Any]) -> list[str]:
    """Validate the `["Amnesia Scroll"]` section shared by common and server TOML files."""
    errors: list[str] = []
    section = _require_section(filename, data, "Amnesia Scroll", errors)
    if section is None:
        return errors

    penalty = section.get("Amnesia scroll penalty")
    if not _is_finite_number(penalty) or not (0.0 <= float(penalty) <= 1.0):
        errors.append(
            f'{filename} invariant violation: ["Amnesia Scroll"]."Amnesia scroll penalty" '
            f"must be a number in 0.0..1.0 (got {penalty!r}) because it represents the percentage "
            "of player levels lost on skill tree reset."
        )

    drop_dragon = section.get("Drop amnesia scrolls from the Ender Dragon")
    if not isinstance(drop_dragon, bool):
        errors.append(
            f'{filename} invariant violation: ["Amnesia Scroll"]."Drop amnesia scrolls from the Ender Dragon" '
            f"must be a boolean (got {drop_dragon!r}) to control Ender Dragon loot table injection."
        )

    return errors


def _validate_experience(filename: str, data: dict[str, Any]) -> list[str]:
    """Validate the `[Experience]` section shared by common and server TOML files."""
    errors: list[str] = []
    section = _require_section(filename, data, "Experience", errors)
    if section is None:
        return errors

    multiplier = section.get("Grindstone experience multiplier")
    if not _is_finite_number(multiplier) or not (0.0 <= float(multiplier) <= 1.0):
        errors.append(
            f'{filename} invariant violation: [Experience]."Grindstone experience multiplier" '
            f"must be a number in 0.0..1.0 (got {multiplier!r}) to prevent grindstone XP duplication "
            "or negative experience grants."
        )

    return errors


def validate_common_toml(data: dict[str, Any]) -> list[str]:
    """Validate architectural and gameplay invariants for `skilltree-common.toml`."""
    errors: list[str] = []
    filename = "skilltree-common.toml"

    errors.extend(_validate_skill_points(filename, data, max_points_upper=1000))

    gems = _require_section(filename, data, "Gems", errors)
    if gems is not None:
        drop_chance = gems.get("Base drop chance")
        if not _is_finite_number(drop_chance) or not (0.0 <= float(drop_chance) <= 1.0):
            errors.append(
                f'{filename} invariant violation: [Gems]."Base drop chance" '
                f"must be a number in 0.0..1.0 (got {drop_chance!r}) because it represents a "
                "probability for gem drops."
            )

    equipment = _require_section(filename, data, "Equipment", errors)
    if equipment is not None:
        for key in EQUIPMENT_SOCKET_KEYS:
            sockets = equipment.get(key)
            if not is_strict_int(sockets) or not (0 <= sockets <= 4):
                errors.append(
                    f'{filename} invariant violation: [Equipment]."{key}" '
                    f"must be an integer in 0..4 (got {sockets!r}) to stay within Passive Skill Tree's "
                    "supported gem socket count per equipment slot."
                )

        blacklist = equipment.get("IDs of items that shouldn't have sockets")
        if not isinstance(blacklist, list) or any(
            not isinstance(item, str) or not item.strip() for item in blacklist
        ):
            errors.append(
                f'{filename} invariant violation: [Equipment]."IDs of items that shouldn\'t have sockets" '
                f"must be a list of non-empty strings (got {blacklist!r}) so item socket blacklisting "
                "parses valid resource locations or wildcard patterns."
            )

    errors.extend(_validate_amnesia_scroll(filename, data))
    errors.extend(_validate_experience(filename, data))

    mixtures = _require_section(filename, data, "Mixtures", errors)
    if mixtures is not None:
        for key in ("Effects duration multiplier", "Effects strength multiplier"):
            val = mixtures.get(key)
            if not _is_finite_number(val) or not (0.0 <= float(val) <= 2.0):
                errors.append(
                    f'{filename} invariant violation: [Mixtures]."{key}" '
                    f"must be a number in 0.0..2.0 (got {val!r}) to stay within Forge's configured "
                    "alchemical mixture balance bounds."
                )

    return errors


def validate_server_toml(data: dict[str, Any]) -> list[str]:
    """Validate server-specific invariants for `skilltree-server.toml`."""
    errors: list[str] = []
    filename = "skilltree-server.toml"

    errors.extend(_validate_skill_points(filename, data, max_points_upper=None))
    errors.extend(_validate_amnesia_scroll(filename, data))
    errors.extend(_validate_experience(filename, data))

    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/skilltree/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            "skilltree-common.toml": validate_common_toml,
            "skilltree-server.toml": validate_server_toml,
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Passive Skill Tree static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "skilltree",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Passive Skill Tree static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
