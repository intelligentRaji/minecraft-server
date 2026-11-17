# Create: Slice & Dice — Configuration Rules (`mods/sliceanddice/`)

## 1. Configuration Scope (`mods/sliceanddice/configs/`)
- Edit Create: Slice & Dice configuration directly inside `mods/sliceanddice/configs/`:
  - `config/sliceanddice-common.toml` — Forge common configuration covering Create Mechanical Harvester knife integration, Slicer tool durability/rotation/JEI recipe conversion, Basin Cooking Farmer's Delight recipe integration and Blaze Burner heat level, and Sprinkler fluid capacity/consumption/range.
- For full section/key schemas, valid ranges, and operational notes, activate the [`sliceanddice-config` skill](file:///home/wakaria/dev/minecraft-server/mods/sliceanddice/.agents/skills/sliceanddice-config/SKILL.md).

## 2. Server Invariants
1. **Valid Forge TOML Syntax & Ranges:**
   - `[basin_cooking].heat_condition` must be one of `"NONE"`, `"HEATED"`, or `"SUPERHEATED"`.
   - `[sprinkler].fluid_capacity` must be an integer within `10 ~ 2048`.
   - `[sprinkler].fluid_per_use` must be an integer within `0 ~ 2048` (and should not exceed `fluid_capacity` if the sprinkler is expected to operate).
   - `[sprinkler].horizontal_range` must be an integer within `1 ~ 32`.
2. **Startup / World-Load Config & Client Sync:**
   - `sliceanddice-common.toml` is a Forge common configuration loaded at startup/world-load (not live-reloadable via RCON); changes require a server restart to take effect.
   - If shared recipe or JEI-display settings change (`[basin_cooking].enabled`, `[basin_cooking].heat_condition`, or `[slicer].jei_show_converted_recipes`), client configs should match the server to prevent recipe/JEI mismatches.

## 3. Sanitized & Excluded Files
- Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/sliceanddice/configs/`.
