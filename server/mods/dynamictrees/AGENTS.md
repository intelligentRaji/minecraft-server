# Dynamic Trees — Configuration Rules (`mods/dynamictrees/`)

## 1. Configuration Scope (`mods/dynamictrees/configs/`)
- Edit Dynamic Trees configuration directly inside `mods/dynamictrees/configs/`:
  - `config/dynamictrees-common.toml` — Forge common configuration covering vanilla tree/sapling replacement, dirt bucket & mega seed recipes, biochar brewing base, and seasonal mod integration.
  - `world/serverconfig/dynamictrees-server.toml` — Forge server configuration covering falling tree leaf particle limits, seed drop/planting/TTL rules, tree growth/harvesting/rot/swamp oak/bone meal settings, player interaction & falling tree damage, world generation & dimension blacklisting, and debug markers.
- For full section/key schemas, valid ranges, and tuning guidance, activate the [`dynamictrees-config` skill](file:///home/wakaria/dev/minecraft-server/mods/dynamictrees/.agents/skills/dynamictrees-config/SKILL.md).

## 2. Server Invariants
1. **Valid Forge TOML Syntax, Sections, Keys & Types:**
   - Preserve exact section headers and key names (note the mod's upstream spelling `enableBranchClimbling` in `[interaction]`).
   - Enforce strict TOML types (booleans, integers, floats, strings, and string arrays); never quote numbers or booleans.
   - Keep `biocharBrewingBase`, `preferredSeasonMod`, and every entry in `dimensionsBlacklist` as non-empty strings.
2. **Enum Values & Numeric Ranges:**
   - `swampOaksInWater` must be one of `"ROOTED"`, `"SUNK"`, or `"DISABLED"`.
   - `axeDamageMode` must be one of `"VANILLA"`, `"THICKNESS"`, or `"VOLUME"`.
   - All numeric values must stay within their Forge-defined bounds (e.g., root `growthFolding` in `0 ~ 4096`, `[trees].growthFolding` in `1 ~ 8`, `[trees].growthMultiplier` in `0.0 ~ 16.0`, `[trees].harvestMultiplier` in `0.0 ~ 128.0`, `[seeds].timeToLive` in `0 ~ 6000`).
3. **Startup / World-Load Reload Discipline:**
   - `config/dynamictrees-common.toml` and `world/serverconfig/dynamictrees-server.toml` are startup/world-load Forge TOML configs (not live-reloadable via RCON); changes require restarting `mc-forge-server` to take effect.

## 3. Sanitized & Excluded Files
- Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/dynamictrees/configs/`.
