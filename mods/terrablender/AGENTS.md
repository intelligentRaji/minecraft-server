# TerraBlender — Configuration Rules (`mods/terrablender/`)

## 1. Configuration Scope (`mods/terrablender/configs/`)
- Edit TerraBlender configuration directly inside `mods/terrablender/configs/`:
  - `config/terrablender.toml` — Top-level `general = {}` empty table and `[generation_settings]` controlling Overworld/Nether biome region sizes (`overworld_region_size`, `nether_region_size`) and vanilla biome region weights (`vanilla_overworld_region_weight`, `vanilla_nether_region_weight`).
- For full section/key schemas, valid ranges, cross-mod interactions, and operational notes, activate the [`terrablender-config` skill](file:///home/wakaria/dev/minecraft-server/mods/terrablender/.agents/skills/terrablender-config/SKILL.md).

## 2. Server Invariants
1. **Valid TOML Types & Ranges:**
   - `general` must remain an empty table (`general = {}`).
   - All four keys under `[generation_settings]` must be strict integers (never booleans or floats):
     - `overworld_region_size` and `nether_region_size`: integer in `2`–`6`.
     - `vanilla_overworld_region_weight` and `vanilla_nether_region_weight`: integer in `0`–`2147483647`.
2. **Startup Config & World-Generation Semantics:**
   - `config/terrablender.toml` is a static startup-only configuration (not live-reloadable via RCON); changes require a server restart to take effect.
   - Modifying region sizes or weights on an existing world only affects newly generated chunks and can cause visible chunk borders between old and new terrain.
3. **Cross-Mod Weight Balancing:**
   - Biomes O' Plenty (`mods/biomesoplenty/configs/config/biomesoplenty/generation.toml`) registers its own TerraBlender region weights that compete directly with `vanilla_overworld_region_weight` and `vanilla_nether_region_weight`.

## 3. Sanitized & Excluded Files
- Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/terrablender/configs/`.
