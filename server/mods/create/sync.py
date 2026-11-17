#!/usr/bin/env python3
"""One-way deterministic configuration placement for Create.

Places static configurations from `mods/create/configs/` into `data/`:
- `config/create-common.toml` -> `data/config/create-common.toml`
- `world/serverconfig/create-server.toml` -> `data/world/serverconfig/create-server.toml`

Validates server invariants, runtime state isolation, and secret guards before touching `data/`.
Never reads, copies, or modifies excluded world/schematic runtime directories
(`data/world/schematics/`, `data/world/data/`, `data/world/playerdata/`, `data/logs/`, `data/mods/`).
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
    is_finite_number,
    is_strict_int,
    run_sync_cli,
    validate_static_configs,
)

REPO_ROOT = MODS_DIR.parent
CONFIGS_DIR = MOD_DIR / "configs"
DATA_DIR = REPO_ROOT / "data"

STATIC_FILES: dict[str, tuple[str, ...]] = {
    "config/create-common.toml": ("config", "create-common.toml"),
    "world/serverconfig/create-server.toml": (
        "world",
        "serverconfig",
        "create-server.toml",
    ),
}

FORBIDDEN_NAMES: frozenset[str] = frozenset({
    "schematics",
    "data",
    "playerdata",
    "region",
    "logs",
    "mods",
})

FORBIDDEN_SUFFIXES: tuple[str, ...] = DEFAULT_FORBIDDEN_SUFFIXES + (
    ".nbt",
    ".dat",
    ".json",
)

CONTRAPTION_MOVEMENT_MODES: frozenset[str] = frozenset({
    "MOVABLE",
    "NO_PICKUP",
    "UNMOVABLE",
})
DEPLOYER_ATTACK_MODES: frozenset[str] = frozenset({"ALL", "CREEPERS", "NONE"})
BOTTOMLESS_FLUID_MODES: frozenset[str] = frozenset({
    "ALLOW_ALL",
    "DENY_ALL",
    "ALLOW_BY_TAG",
    "DENY_BY_TAG",
})


def _require_table(
    filename: str,
    root: dict[str, Any],
    path: tuple[str, ...],
    errors: list[str],
) -> dict[str, Any] | None:
    """Traverse `path` in `root` and return the nested dict, or record an invariant error."""
    current: Any = root
    dotted = ".".join(path)
    for part in path:
        if not isinstance(current, dict) or part not in current:
            errors.append(
                f"{filename} invariant violation: [{dotted}] table must be present "
                "so Forge/Create can load all required server configuration settings."
            )
            return None
        current = current[part]
    if not isinstance(current, dict):
        errors.append(
            f"{filename} invariant violation: [{dotted}] must be a TOML table "
            f"(got {type(current).__name__}) so Forge/Create can parse its keys."
        )
        return None
    return current


def _check_bools(
    filename: str,
    section_name: str,
    table: dict[str, Any],
    keys: tuple[str, ...],
    rationale: str,
    errors: list[str],
) -> None:
    for key in keys:
        val = table.get(key)
        if not isinstance(val, bool):
            errors.append(
                f"{filename} invariant violation: [{section_name}].{key} "
                f"must be a boolean (got {val!r}) to {rationale}."
            )


def _check_int_bounds(
    filename: str,
    section_name: str,
    table: dict[str, Any],
    specs: tuple[tuple[str, int, int | None], ...],
    rationale: str,
    errors: list[str],
) -> None:
    for key, min_val, max_val in specs:
        val = table.get(key)
        if max_val is None:
            valid = is_strict_int(val) and val >= min_val
            expected = f">= {min_val}" if min_val <= 0 else f"> {min_val - 1}"
        else:
            valid = is_strict_int(val) and min_val <= val <= max_val
            expected = f"in {min_val}..{max_val}"
        if not valid:
            errors.append(
                f"{filename} invariant violation: [{section_name}].{key} "
                f"must be an integer {expected} (got {val!r}) to {rationale}."
            )


def _check_float_bounds(
    filename: str,
    section_name: str,
    table: dict[str, Any],
    specs: tuple[tuple[str, float, float | None], ...],
    rationale: str,
    errors: list[str],
) -> None:
    for key, min_val, max_val in specs:
        val = table.get(key)
        if not is_finite_number(val):
            valid = False
        elif max_val is None:
            valid = float(val) >= min_val
        else:
            valid = min_val <= float(val) <= max_val
        expected = f"in {min_val}..{max_val}" if max_val is not None else f">= {min_val}"
        if not valid:
            errors.append(
                f"{filename} invariant violation: [{section_name}].{key} "
                f"must be a finite number {expected} (got {val!r}) to {rationale}."
            )


def _check_enums(
    filename: str,
    section_name: str,
    table: dict[str, Any],
    specs: tuple[tuple[str, frozenset[str]], ...],
    rationale: str,
    errors: list[str],
) -> None:
    for key, allowed in specs:
        val = table.get(key)
        if not isinstance(val, str) or val not in allowed:
            allowed_str = ", ".join(sorted(allowed))
            errors.append(
                f"{filename} invariant violation: [{section_name}].{key} "
                f"must be one of {{{allowed_str}}} (got {val!r}) to {rationale}."
            )


def validate_common_toml(data: dict[str, Any]) -> list[str]:
    """Validate invariants for `config/create-common.toml`."""
    errors: list[str] = []
    filename = "config/create-common.toml"
    worldgen = _require_table(filename, data, ("worldgen",), errors)
    if worldgen is not None:
        _check_bools(
            filename,
            "worldgen",
            worldgen,
            ("disableWorldGen",),
            "deterministically control Create ore and terrain world generation",
            errors,
        )
    return errors


def _validate_kinetics(filename: str, data: dict[str, Any], errors: list[str]) -> None:
    kinetics = _require_table(filename, data, ("kinetics",), errors)
    if kinetics is not None:
        _check_bools(
            filename,
            "kinetics",
            kinetics,
            ("disableStress",),
            "control whether Create's kinetic stress mechanic is enforced server-wide",
            errors,
        )
        _check_int_bounds(
            filename,
            "kinetics",
            kinetics,
            (
                ("maxBeltLength", 6, None),
                ("maxChainConveyorLength", 6, None),
                ("maxChainConveyorConnections", 2, None),
                ("crushingDamage", 0, None),
                ("maxRotationSpeed", 65, None),
                ("kineticValidationFrequency", 6, None),
                ("minimumWindmillSails", 0, None),
                ("windmillSailsPerRPM", 2, None),
                ("maxEjectorDistance", 0, None),
                ("ejectorScanInterval", 11, None),
            ),
            "stay within Forge's kinetic range bounds and prevent lag-inducing mechanical networks",
            errors,
        )
        _check_float_bounds(
            filename,
            "kinetics",
            kinetics,
            (("crankHungerMultiplier", 0.0, 1.0),),
            "keep manual crank exhaustion within Forge's 0.0..1.0 multiplier bounds",
            errors,
        )
        _check_enums(
            filename,
            "kinetics",
            kinetics,
            (("ignoreDeployerAttacks", DEPLOYER_ATTACK_MODES),),
            "use a valid Create deployer aggro filter enum",
            errors,
        )

    encased_fan = _require_table(filename, data, ("kinetics", "encasedFan"), errors)
    if encased_fan is not None:
        _check_int_bounds(
            filename,
            "kinetics.encasedFan",
            encased_fan,
            (
                ("fanPushDistance", 6, None),
                ("fanPullDistance", 6, None),
                ("fanBlockCheckRate", 11, None),
                ("fanRotationArgmax", 65, None),
                ("fanProcessingTime", 0, None),
            ),
            "keep Encased Fan raycasts and processing ticks within Forge's server bounds",
            errors,
        )

    contraptions = _require_table(filename, data, ("kinetics", "contraptions"), errors)
    if contraptions is not None:
        _check_int_bounds(
            filename,
            "kinetics.contraptions",
            contraptions,
            (
                ("maxBlocksMoved", 2, None),
                ("maxChassisRange", 2, None),
                ("maxPistonPoles", 2, None),
                ("maxRopeLength", 2, None),
                ("maxCartCouplingLength", 2, None),
                ("rollerFillDepth", 2, None),
            ),
            "bound contraption assembly sizes and avoid server tick stalls",
            errors,
        )
        _check_enums(
            filename,
            "kinetics.contraptions",
            contraptions,
            (
                ("movableSpawners", CONTRAPTION_MOVEMENT_MODES),
                ("amethystMovement", CONTRAPTION_MOVEMENT_MODES),
                ("movableObsidian", CONTRAPTION_MOVEMENT_MODES),
                ("movableReinforcedDeepslate", CONTRAPTION_MOVEMENT_MODES),
            ),
            "enforce valid Create block-movement policies for protected blocks",
            errors,
        )
        _check_bools(
            filename,
            "kinetics.contraptions",
            contraptions,
            (
                "survivalContraptionPickup",
                "moveItemsToStorage",
                "harvestPartiallyGrown",
                "harvesterReplants",
                "minecartContraptionInContainers",
                "stabiliseStableContraptions",
                "syncPlayerPickupHitboxWithContraptionHitbox",
                "noDropWhenContraptionReplaceBlocks",
            ),
            "deterministically control contraption harvesting, pickup, and collision behavior",
            errors,
        )

    stats = _require_table(filename, data, ("kinetics", "stats"), errors)
    if stats is not None:
        _check_float_bounds(
            filename,
            "kinetics.stats",
            stats,
            (
                ("mediumSpeed", 0.0, 4096.0),
                ("fastSpeed", 0.0, 65535.0),
                ("mediumStressImpact", 0.0, 4096.0),
                ("highStressImpact", 0.0, 65535.0),
                ("mediumCapacity", 0.0, 4096.0),
                ("highCapacity", 0.0, 65535.0),
            ),
            "keep kinetic tooltip thresholds within Create's Forge config bounds",
            errors,
        )

    for subkey in ("impact", "capacity"):
        table = _require_table(
            filename, data, ("kinetics", "stressValues", "v2", subkey), errors
        )
        if table is None:
            continue
        if not table:
            errors.append(
                f"{filename} invariant violation: [kinetics.stressValues.v2.{subkey}] "
                "must not be empty so Create retains explicit stress definitions for kinetic blocks."
            )
            continue
        for block_id, val in sorted(table.items()):
            if not is_finite_number(val) or float(val) < 0.0:
                errors.append(
                    f"{filename} invariant violation: [kinetics.stressValues.v2.{subkey}].{block_id} "
                    f"must be a non-negative finite number (got {val!r}) so stress calculations remain valid."
                )


def _validate_trains(filename: str, data: dict[str, Any], errors: list[str]) -> None:
    trains = _require_table(filename, data, ("trains",), errors)
    if trains is not None:
        _check_bools(
            filename,
            "trains",
            trains,
            ("trainsCauseDamage",),
            "control whether moving trains deal collision damage",
            errors,
        )
        _check_int_bounds(
            filename,
            "trains",
            trains,
            (
                ("maxTrackPlacementLength", 16, 128),
                ("maxAssemblyLength", 6, None),
                ("maxBogeyCount", 2, None),
            ),
            "stay within Forge's railway track and train assembly bounds",
            errors,
        )
        _check_float_bounds(
            filename,
            "trains",
            trains,
            (("manualTrainSpeedModifier", 0.0, None),),
            "keep manual train speed scaling non-negative and finite",
            errors,
        )

    train_stats = _require_table(filename, data, ("trains", "trainStats"), errors)
    if train_stats is not None:
        _check_float_bounds(
            filename,
            "trains.trainStats",
            train_stats,
            (
                ("trainTopSpeed", 0.0, None),
                ("trainTurningTopSpeed", 0.0, None),
                ("trainAcceleration", 0.0, None),
            ),
            "keep standard train physics non-negative and finite",
            errors,
        )

    powered_stats = _require_table(
        filename, data, ("trains", "poweredTrainStats"), errors
    )
    if powered_stats is not None:
        _check_float_bounds(
            filename,
            "trains.poweredTrainStats",
            powered_stats,
            (
                ("poweredTrainTopSpeed", 0.0, None),
                ("poweredTrainTurningTopSpeed", 0.0, None),
                ("poweredTrainAcceleration", 0.0, None),
            ),
            "keep powered train physics non-negative and finite",
            errors,
        )


def validate_server_toml(data: dict[str, Any]) -> list[str]:
    """Validate server-specific invariants for `world/serverconfig/create-server.toml`."""
    errors: list[str] = []
    filename = "world/serverconfig/create-server.toml"

    infra = _require_table(filename, data, ("infrastructure",), errors)
    if infra is not None:
        _check_int_bounds(
            filename,
            "infrastructure",
            infra,
            (("tickrateSyncTimer", 6, None),),
            "keep tickrate synchronization packet intervals above Forge's minimum (> 5 ticks)",
            errors,
        )

    recipes = _require_table(filename, data, ("recipes",), errors)
    if recipes is not None:
        _check_bools(
            filename,
            "recipes",
            recipes,
            (
                "bulkPressing",
                "bulkCutting",
                "allowBrewingInMixer",
                "allowShapelessInMixer",
                "allowShapedSquareInPress",
                "allowRegularCraftingInCrafter",
                "allowStonecuttingOnSaw",
                "allowCastingBySpout",
                "displayLogStrippingRecipes",
                "enableRefinedRadianceRecipe",
                "enableShadowSteelRecipe",
            ),
            "deterministically configure Create's recipe compatibility toggles",
            errors,
        )
        _check_int_bounds(
            filename,
            "recipes",
            recipes,
            (
                ("maxFireworkIngredientsInCrafter", 2, None),
                ("lightSourceCountForRefinedRadiance", 2, None),
            ),
            "satisfy Forge's minimum (> 1) recipe crafting thresholds",
            errors,
        )

    _validate_kinetics(filename, data, errors)

    fluids = _require_table(filename, data, ("fluids",), errors)
    if fluids is not None:
        _check_int_bounds(
            filename,
            "fluids",
            fluids,
            (
                ("fluidTankCapacity", 2, None),
                ("fluidTankMaxHeight", 2, None),
                ("mechanicalPumpRange", 2, None),
                ("hosePulleyRange", 2, None),
                ("hosePulleyBlockThreshold", -1, None),
            ),
            "keep fluid tank capacities, pump ranges, and infinite-source thresholds within Forge bounds",
            errors,
        )
        _check_enums(
            filename,
            "fluids",
            fluids,
            (("bottomlessFluidMode", BOTTOMLESS_FLUID_MODES),),
            "use a valid Create bottomless fluid policy enum",
            errors,
        )
        _check_bools(
            filename,
            "fluids",
            fluids,
            (
                "fillInfinite",
                "fluidFillPlaceFluidSourceBlocks",
                "pipesPlaceFluidSourceBlocks",
            ),
            "control fluid source placement and infinite-draining behavior",
            errors,
        )

    logistics = _require_table(filename, data, ("logistics",), errors)
    if logistics is not None:
        _check_int_bounds(
            filename,
            "logistics",
            logistics,
            (
                ("defaultExtractionTimer", 2, None),
                ("psiTimeout", 2, None),
                ("mechanicalArmRange", 2, None),
                ("packagePortRange", 2, None),
                ("linkRange", 2, None),
                ("displayLinkRange", 2, None),
                ("vaultCapacity", 1, 2048),
                ("chainConveyorCapacity", 2, None),
                ("brassTunnelTimer", 1, 10),
                ("factoryGaugeTimer", 6, None),
            ),
            "keep logistics ranges, timers, and vault capacities within Forge's server bounds",
            errors,
        )
        _check_bools(
            filename,
            "logistics",
            logistics,
            ("seatHostileMobs",),
            "control whether hostile mobs can mount Create seats",
            errors,
        )

    schematics = _require_table(filename, data, ("schematics",), errors)
    if schematics is not None:
        _check_bools(
            filename,
            "schematics",
            schematics,
            ("creativePrintIncludesAir",),
            "control whether Creative schematic placement overwrites blocks with air",
            errors,
        )
        _check_int_bounds(
            filename,
            "schematics",
            schematics,
            (
                ("maxSchematics", 2, None),
                ("maxTotalSchematicSize", 17, None),
                ("maxSchematicPacketSize", 256, 32767),
                ("schematicIdleTimeout", 101, None),
            ),
            "bound schematic uploads and packet sizes to protect server memory and network bandwidth",
            errors,
        )

    cannon = _require_table(
        filename, data, ("schematics", "schematicannon"), errors
    )
    if cannon is not None:
        _check_int_bounds(
            filename,
            "schematics.schematicannon",
            cannon,
            (
                ("schematicannonDelay", 2, None),
                ("schematicannonShotsPerGunpowder", 2, None),
            ),
            "keep Schematicannon firing rate and gunpowder efficiency within Forge bounds",
            errors,
        )

    equipment = _require_table(filename, data, ("equipment",), errors)
    if equipment is not None:
        _check_int_bounds(
            filename,
            "equipment",
            equipment,
            (
                ("maxSymmetryWandRange", 11, None),
                ("placementAssistRange", 4, None),
                ("toolboxRange", 2, None),
                ("airInBacktank", 2, None),
                ("enchantedBacktankCapacity", 2, None),
                ("maxExtendoGripActions", 0, None),
                ("maxPotatoCannonShots", 0, None),
            ),
            "keep Create equipment ranges and backtank durability/air capacities within Forge bounds",
            errors,
        )

    _validate_trains(filename, data, errors)
    return errors


def validate_configs() -> dict[str, bytes]:
    """Validate all static config files in `mods/create/configs/` before placement."""
    return validate_static_configs(
        CONFIGS_DIR,
        STATIC_FILES,
        {
            "config/create-common.toml": validate_common_toml,
            "world/serverconfig/create-server.toml": validate_server_toml,
        },
        forbidden_names=FORBIDDEN_NAMES,
        forbidden_suffixes=FORBIDDEN_SUFFIXES,
    )


def apply_configs(loaded_bytes: dict[str, bytes], dry_run: bool) -> tuple[int, int]:
    """Place validated Create static files into `DATA_DIR`."""
    return apply_static_files(STATIC_FILES, DATA_DIR, loaded_bytes, dry_run)


def main(argv: list[str] | None = None) -> int:
    return run_sync_cli(
        "create",
        validate_configs,
        apply_configs,
        argv=argv,
        description="Validate and atomically place Create static configs into data/.",
    )


if __name__ == "__main__":
    sys.exit(main())
