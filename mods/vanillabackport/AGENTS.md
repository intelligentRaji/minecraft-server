# Vanilla Backport — Configuration Rules (`mods/vanillabackport/`)

## 1. Configuration Scope (`mods/vanillabackport/configs/`)
- Edit Vanilla Backport configuration directly inside `mods/vanillabackport/configs/`:
  - `config/vanillabackport-common.toml` — Forge common TOML configuration across 11 update sections (`["Tricky Trials"]`, `["Armored Paws"]`, `["Bundles of Bravery"]`, `["The Garden Awakens"]`, `["Spring to Life"]`, `["Chase the Skies"]`, `["Hot as Lava"]`, `["Copper Age"]`, `["Mounts of Mayhem"]`, `["Chaos Cubed"]`, and `["Wilderness Bound"]`).
- For full section/key schemas, valid ranges, current server values, and operational notes, activate the [`vanillabackport-config` skill](file:///home/wakaria/dev/minecraft-server/mods/vanillabackport/.agents/skills/vanillabackport-config/SKILL.md).

## 2. Server Invariants
1. **Valid Forge TOML Structure & Strict Types:**
   - All 11 TOML tables and their exact keys must remain present with strict types (booleans, integers, floats/numbers, or strings).
2. **Recipe Mode Keys:**
   - `bundle_recipe`, `lead_recipe`, `saddle_recipe`, and `lodestone_recipe` must be `"APPEND"`, `"REPLACE"`, or `"IGNORE"`.
3. **24-bit RGB Color Keys:**
   - `creaking_particle_color` and `creaking_particle_reverse_color` must be 24-bit RGB integers (`0` to `16777215` / `0xFFFFFF`).
4. **Probability & Speed Keys:**
   - `mob_variants_spawn_chance`, `cactus_flower_spawn_chance`, and `zombie_nautilus_spawn_chance` must be finite numbers in `0.0..1.0`.
   - `happy_ghast_speed_modifier` must be a finite number `>= 0.0`.
5. **Copper Age Golem Keys:**
   - `golem_weathering_tick_from > 0`, `golem_weathering_tick_to > 0`, and `golem_weathering_tick_from <= golem_weathering_tick_to`.
   - `golem_item_carry_amount > 1`.
6. **Startup Config & World-Generation Semantics:**
   - `config/vanillabackport-common.toml` is a startup-only Forge common configuration (not live-reloadable via RCON); changes require a server restart to take effect.
   - Worldgen toggles (such as `pale_garden`, `has_sulfur_caves`, `has_sulfur_springs`, `has_dappled_forest`, `fallen_trees`, `bushes`, `firefly_bushes`, `wildflowers`, `dry_grass`, `leaf_litter`, and `cactus_flowers`) only affect newly generated chunks; existing generated chunks remain unchanged.

## 3. Sanitized & Excluded Files
- Never place runtime or world state (`logs/`, `world/`, `mods/`) or binary/log/secret artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/vanillabackport/configs/`.
