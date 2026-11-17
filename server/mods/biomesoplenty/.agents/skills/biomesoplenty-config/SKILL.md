---
name: biomesoplenty-config
description: Inspect and configure Biomes O' Plenty server-side settings (biome generation toggles, Wandering Trader trades, and TerraBlender Overworld/Nether region weights) in mods/biomesoplenty/configs/.
---

# Biomes O' Plenty Configuration Guide (`biomesoplenty-config`)

Use this skill to inspect and modify **Biomes O' Plenty** (`modpack/server-client/BiomesOPlenty-forge-1.20.1-19.0.0.96.jar`) configuration in `mods/biomesoplenty/configs/`.

> **Startup & World-Generation Config:** All three files under `config/biomesoplenty/` are static server-side configurations (not live-reloadable via RCON); changes require a server restart to take effect. Toggling biomes or changing region weights only affects **newly generated chunks**—existing generated chunks remain unchanged.

---

## 1. Configuration File Overview (`mods/biomesoplenty/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/biomesoplenty/biome_toggles.json` | 66 boolean toggles (`aspen_glade_enabled` through `woodland_enabled`) enabling or disabling individual Biomes O' Plenty biomes during world generation. | JSON |
| `config/biomesoplenty/gameplay.toml` | Gameplay settings: Wandering Trader trade pool additions. | TOML |
| `config/biomesoplenty/generation.toml` | TerraBlender region weightings for Biomes O' Plenty biomes in the Nether and Overworld. | TOML |

---

## 2. `config/biomesoplenty/biome_toggles.json` Reference

Top-level JSON object mapping each of the 66 Biomes O' Plenty biome toggle keys to a strict boolean (`true` or `false`, all `true` by default). Every key must remain present.

- **A–F:** `aspen_glade_enabled`, `auroral_garden_enabled`, `bayou_enabled`, `bog_enabled`, `cold_desert_enabled`, `coniferous_forest_enabled`, `crag_enabled`, `crystalline_chasm_enabled`, `dead_forest_enabled`, `dryland_enabled`, `dune_beach_enabled`, `erupting_inferno_enabled`, `field_enabled`, `fir_clearing_enabled`, `floodplain_enabled`, `forested_field_enabled`, `fungal_jungle_enabled`
- **G–M:** `glowing_grotto_enabled`, `grassland_enabled`, `gravel_beach_enabled`, `highland_enabled`, `hot_springs_enabled`, `jacaranda_glade_enabled`, `jade_cliffs_enabled`, `lavender_field_enabled`, `lush_desert_enabled`, `lush_savanna_enabled`, `maple_woods_enabled`, `marsh_enabled`, `mediterranean_forest_enabled`, `moor_enabled`, `muskeg_enabled`, `mystic_grove_enabled`
- **O–S:** `old_growth_dead_forest_enabled`, `old_growth_woodland_enabled`, `ominous_woods_enabled`, `orchard_enabled`, `origin_valley_enabled`, `overgrown_greens_enabled`, `pasture_enabled`, `prairie_enabled`, `pumpkin_patch_enabled`, `rainforest_enabled`, `redwood_forest_enabled`, `rocky_rainforest_enabled`, `rocky_shrubland_enabled`, `scrubland_enabled`, `seasonal_forest_enabled`, `shrubland_enabled`, `snowblossom_grove_enabled`, `snowy_coniferous_forest_enabled`, `snowy_fir_clearing_enabled`, `snowy_maple_woods_enabled`, `spider_nest_enabled`
- **T–W:** `tropics_enabled`, `tundra_enabled`, `undergrowth_enabled`, `visceral_heap_enabled`, `volcanic_plains_enabled`, `volcano_enabled`, `wasteland_enabled`, `wasteland_steppe_enabled`, `wetland_enabled`, `wintry_origin_valley_enabled`, `withered_abyss_enabled`, `woodland_enabled`

---

## 3. `config/biomesoplenty/gameplay.toml` Reference

### `[general]`
- `wandering_trader_trades` (boolean, default `true`): Adds various Biomes O' Plenty resources to the Wandering Trader trade pool.

---

## 4. `config/biomesoplenty/generation.toml` Reference

Controls TerraBlender region weights for Biomes O' Plenty. Higher values increase the relative frequency of Biomes O' Plenty regions compared to vanilla and other biome mods; `0` disables the region.

### `[nether]`
- `bop_nether_region_weight` (integer `>= 0`, default `13`): Weighting of Biomes O' Plenty biome regions in the Nether.
- `bop_nether_rare_region_weight` (integer `>= 0`, default `2`): Weighting of rare Biomes O' Plenty biome regions in the Nether.

### `[overworld]`
- `bop_primary_overworld_region_weight` (integer `>= 0`, default `10`): Weighting of primary Biomes O' Plenty biome regions in the Overworld.
- `bop_overworld_rare_region_weight` (integer `>= 0`, default `2`): Weighting of rare Biomes O' Plenty biome regions in the Overworld.
- `bop_secondary_overworld_region_weight` (integer `>= 0`, default `8`): Weighting of secondary Biomes O' Plenty biome regions in the Overworld.

---

## 5. Mandatory Invariants

1. **Valid JSON & TOML Types and Ranges:**
   - Keep all 66 keys present in `biome_toggles.json` with strict boolean values (`true` or `false`).
   - Keep `wandering_trader_trades` as a strict boolean (`true` or `false`).
   - Keep all five region weight settings in `generation.toml` as non-negative integers (`>= 0`).
2. **Restart & Chunk-Generation Discipline:**
   - Restart the server after modifying any file under `config/biomesoplenty/`.
   - Remember that biome toggle and region weight changes only apply to newly generated chunks; existing chunks are unaffected.
3. **Excluded Runtime & World State:**
   - Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/biomesoplenty/configs/`.
