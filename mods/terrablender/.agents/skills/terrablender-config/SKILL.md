---
name: terrablender-config
description: Inspect and configure TerraBlender server-side settings (Overworld/Nether biome region sizes and vanilla region weights) in mods/terrablender/configs/.
---

# TerraBlender Configuration Guide (`terrablender-config`)

Use this skill to inspect and modify **TerraBlender** (`modpack/server-client/TerraBlender-forge-1.20.1-3.0.1.11.jar`) configuration in `mods/terrablender/configs/`.

> **Startup & World-Generation Config:** `config/terrablender.toml` is a static startup-only worldgen configuration (not live-reloadable via RCON); changes require a server restart to take effect. Modifying region sizes or weights on an existing world only affects **newly generated chunks** and can cause visible chunk borders where new terrain meets existing chunks.

---

## 1. Configuration File Overview (`mods/terrablender/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/terrablender.toml` | Controls biome region sizes for TerraBlender-integrated mods and relative region weights for vanilla Overworld and Nether biomes. | TOML |

---

## 2. `config/terrablender.toml` Reference

### Top-Level Table: `general`
- `general = {}` — Empty table. Must remain `{}`.

### `[generation_settings]`
Controls how TerraBlender partitions biome regions across mods and weights vanilla biome regions relative to modded regions.

| Key | Type & Range | Default / Current | Description |
| :--- | :--- | :--- | :--- |
| `overworld_region_size` | integer (`2`–`6`) | `4` | Size of Overworld biome regions from each mod that uses TerraBlender. |
| `nether_region_size` | integer (`2`–`6`) | `2` | Size of Nether biome regions from each mod that uses TerraBlender. |
| `vanilla_overworld_region_weight` | integer (`0`–`2147483647`) | `10` | Weighting of vanilla biome regions in the Overworld. |
| `vanilla_nether_region_weight` | integer (`0`–`2147483647`) | `10` | Weighting of vanilla biome regions in the Nether. |

---

## 3. Cross-Mod Interaction (Biomes O' Plenty)

- TerraBlender allocates Overworld and Nether regions proportionally based on each region's configured weight.
- **Biomes O' Plenty** (`mods/biomesoplenty/configs/config/biomesoplenty/generation.toml`) registers its own TerraBlender region weights (`bop_primary_overworld_region_weight`, `bop_overworld_rare_region_weight`, `bop_secondary_overworld_region_weight`, `bop_nether_region_weight`, `bop_nether_rare_region_weight`) that compete directly with `vanilla_overworld_region_weight` and `vanilla_nether_region_weight`.
- Increasing `vanilla_overworld_region_weight` or `vanilla_nether_region_weight` increases the share of vanilla biome regions relative to modded regions; setting a weight to `0` removes vanilla regions from that dimension's TerraBlender pool.

---

## 4. Mandatory Invariants

1. **Valid TOML Types & Ranges:**
   - Keep `general = {}` as an empty table.
   - Keep all four keys under `[generation_settings]` as strict integers (never booleans or floats):
     - `overworld_region_size` and `nether_region_size` must be within `2`–`6`.
     - `vanilla_overworld_region_weight` and `vanilla_nether_region_weight` must be within `0`–`2147483647`.
2. **Restart & Chunk-Generation Discipline:**
   - Restart the server after modifying `config/terrablender.toml`.
   - Region size and weight changes only apply to newly generated chunks and can introduce chunk borders on existing worlds.
3. **Excluded Runtime & World State:**
   - Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/terrablender/configs/`.
