# Biomes O' Plenty — Configuration Rules (`mods/biomesoplenty/`)

## 1. Configuration Scope (`mods/biomesoplenty/configs/`)
- Edit Biomes O' Plenty configuration directly inside `mods/biomesoplenty/configs/`:
  - `config/biomesoplenty/biome_toggles.json` — JSON object of 66 boolean toggles (`aspen_glade_enabled` through `woodland_enabled`) controlling whether each Biomes O' Plenty biome can generate.
  - `config/biomesoplenty/gameplay.toml` — `[general].wandering_trader_trades` (boolean) controlling whether Biomes O' Plenty resources are added to the Wandering Trader trade pool.
  - `config/biomesoplenty/generation.toml` — TerraBlender region weightings under `[nether]` (`bop_nether_region_weight`, `bop_nether_rare_region_weight`) and `[overworld]` (`bop_primary_overworld_region_weight`, `bop_overworld_rare_region_weight`, `bop_secondary_overworld_region_weight`).
- For full section/key schemas, all 66 biome toggle keys, valid ranges, and operational notes, activate the [`biomesoplenty-config` skill](file:///home/wakaria/dev/minecraft-server/mods/biomesoplenty/.agents/skills/biomesoplenty-config/SKILL.md).

## 2. Server Invariants
1. **Valid JSON & Forge TOML Types and Ranges:**
   - `config/biomesoplenty/biome_toggles.json` must be valid JSON containing all 66 biome keys with strict boolean values (`true` or `false`).
   - `wandering_trader_trades` in `config/biomesoplenty/gameplay.toml` must be a strict boolean (`true` or `false`).
   - All five region weight keys in `config/biomesoplenty/generation.toml` must be non-negative integers (`>= 0`).
2. **Startup Config & World-Generation Semantics:**
   - All three files are static server-side configurations (not live-reloadable via RCON); changes require a server restart to take effect.
   - Toggling biomes or changing region weights only affects newly generated chunks; existing generated chunks remain unchanged.

## 3. Sanitized & Excluded Files
- Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/biomesoplenty/configs/`.
