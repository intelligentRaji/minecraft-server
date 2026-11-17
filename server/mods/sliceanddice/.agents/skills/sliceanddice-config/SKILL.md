---
name: sliceanddice-config
description: Inspect and configure Create: Slice & Dice common settings (Mechanical Harvester knife behavior, Slicer, Basin Cooking, and Sprinkler) in mods/sliceanddice/configs/.
---

# Create: Slice & Dice Configuration Guide (`sliceanddice-config`)

Use this skill to inspect and modify **Create: Slice & Dice** (`modpack/server-client/sliceanddice-forge-3.6.0.jar`) configuration in `mods/sliceanddice/configs/`.

> **Startup / World-Load Forge TOML Config:** `config/sliceanddice-common.toml` is not live-reloadable via RCON; changes require a server restart to take effect. When modifying shared recipe or JEI settings (`[basin_cooking].enabled`, `[basin_cooking].heat_condition`, or `[slicer].jei_show_converted_recipes`), keep client configurations aligned with the server to avoid recipe or JEI display mismatches.

---

## 1. Configuration File Overview (`mods/sliceanddice/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/sliceanddice-common.toml` | Forge common settings: Mechanical Harvester knife integration, Slicer durability/rotation/JEI behavior, Basin Cooking Farmer's Delight integration & heat level, and Sprinkler tank capacity/consumption/range. | TOML |

---

## 2. `config/sliceanddice-common.toml` Reference

### `[harvester]`
- `uses_knife` (boolean, default `true`): Whether the Create Mechanical Harvester uses Farmer's Delight knife / cutting behavior when harvesting.

### `[slicer]`
- `consume_tool_durability` (boolean, default `true`): Whether the Slicer consumes durability of the inserted cutting tool.
- `ignore_rotation` (boolean, default `false`): Whether the Slicer ignores rotational direction/orientation constraints.
- `jei_show_converted_recipes` (boolean, default `false`): Whether JEI displays converted Farmer's Delight cutting board recipes for the Slicer. *(Shared client/server JEI setting.)*

### `[basin_cooking]`
- `enabled` (boolean, default `true`): Enables Farmer's Delight cooking pot recipes inside Create Basins. *(Shared client/server recipe setting.)*
- `replace_fluid_containers` (boolean, default `true`): Replaces fluid containers when processing basin cooking recipes.
- `heat_condition` (string enum, default `"HEATED"`): Required Blaze Burner heat level for basin cooking recipes. *(Shared client/server recipe setting.)*
  - **Allowed values:** `"NONE"`, `"HEATED"`, `"SUPERHEATED"`.

### `[sprinkler]`
- `fluid_capacity` (integer `10 ~ 2048`, default `300`): Internal fluid tank capacity (in mB) of the Sprinkler.
- `fluid_per_use` (integer `0 ~ 2048`, default `100`): Fluid consumed (in mB) per Sprinkler activation.
- `horizontal_range` (integer `1 ~ 32`, default `5`): Horizontal radius (in blocks) watered by the Sprinkler.

---

## 3. Mandatory Invariants

1. **Valid Forge TOML Types, Enums & Ranges:**
   - Keep `[basin_cooking].heat_condition` strictly to `"NONE"`, `"HEATED"`, or `"SUPERHEATED"`.
   - Keep `[sprinkler].fluid_capacity` within `10 ~ 2048`.
   - Keep `[sprinkler].fluid_per_use` within `0 ~ 2048` (and at or below `fluid_capacity` for functional operation).
   - Keep `[sprinkler].horizontal_range` within `1 ~ 32`.
2. **Restart & Client-Sync Discipline:**
   - `config/sliceanddice-common.toml` is loaded at startup/world-load and is not live-reloadable via RCON; restart the server after changes.
   - Keep client configurations aligned with the server when modifying `[basin_cooking].enabled`, `[basin_cooking].heat_condition`, or `[slicer].jei_show_converted_recipes`.
3. **Excluded Runtime & World State:**
   - Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/sliceanddice/configs/`.
