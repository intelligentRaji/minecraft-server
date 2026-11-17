---
name: vanillabackport-config
description: Inspect and configure Vanilla Backport common settings (Tricky Trials, Armored Paws, Bundles of Bravery, The Garden Awakens, Spring to Life, Chase the Skies, Hot as Lava, Copper Age, Mounts of Mayhem, Chaos Cubed, and Wilderness Bound) in mods/vanillabackport/configs/.
---

# Vanilla Backport Configuration Guide (`vanillabackport-config`)

Use this skill to inspect and modify **Vanilla Backport** (`modpack/server-client/VanillaBackport-forge-1.20.1-1.2.2.jar`) configuration in `mods/vanillabackport/configs/`.

> **Startup & World-Generation Config:** `config/vanillabackport-common.toml` is a startup-only Forge common configuration (not live-reloadable via RCON); any edits require a server restart to take effect. Worldgen toggles (e.g., `pale_garden`, `has_sulfur_caves`, `has_dappled_forest`, `fallen_trees`, foliage, and loot/feature generation) only affect **newly generated chunks**—existing generated chunks remain unchanged.

---

## 1. Configuration File Overview (`mods/vanillabackport/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/vanillabackport-common.toml` | Forge common settings across 11 update sections controlling backported blocks, mobs, biomes, recipes, loot, and mechanics. | TOML |

---

## 2. `config/vanillabackport-common.toml` Reference

### `["Tricky Trials"]`
- `tuff_blocks` (boolean, current `true`): Allow the Tuff block variants to be obtained.
- `copper_blockset` (boolean, current `true`): Allow the Copper block-set and its variants to be obtained.

### `["Armored Paws"]`
- `armadillo` (boolean, current `false`): Allow armadillos to generate in the Overworld.
- `wolf_variants` (boolean, current `false`): Allow variants for wolves to generate.
- `updated_wolf_spawns` (boolean, current `false`): Add wolves to more biomes for natural spawning.

### `["Bundles of Bravery"]`
- `has_updated_bundles` (boolean, current `true`): Enable the modern bundle interface and controls.
- `bundle_loot` (boolean, current `true`): Allow Bundles to generate in Village loot chests.
- `has_dyeable_bundle_recipe` (boolean, current `true`): Allow bundles to be dyed.
- `inverted_bundle_controls` (boolean, current `false`): Invert the bundle click controls.
- `bundle_recipe` (string: `"APPEND"`, `"REPLACE"`, or `"IGNORE"`, current `"APPEND"`): Apply the modern recipe for bundles.

### `["The Garden Awakens"]`
- `resin` (boolean, current `false`): Allow Resin to be obtained from Creaking Hearts.
- `resin_loot` (boolean, current `false`): Allow Resin to generate in Woodland Mansion loot chests.
- `creaking` (boolean, current `false`): Allow Creakings to spawn from Creaking Hearts.
- `pale_garden` (boolean, current `false`): Allow Pale Garden biomes to generate.
- `pale_trades` (boolean, current `false`): Allow Wandering Traders to offer items from The Garden Awakens.
- `creaking_particle_color` (integer `0..16777215`, current `6250335`): Primary 24-bit RGB color of Creaking Heart trail particles.
- `creaking_particle_reverse_color` (integer `0..16777215`, current `16545810`): Secondary 24-bit RGB color of Creaking Heart trail particles.
- `do_creaking_hearts_work_on_day` (boolean, current `false`): Allow Creaking Hearts to spawn Creakings during the day.
- `lead_recipe` (string: `"APPEND"`, `"REPLACE"`, or `"IGNORE"`, current `"APPEND"`): Apply the modern recipe for leads.
- `saddle_recipe` (string: `"APPEND"`, `"REPLACE"`, or `"IGNORE"`, current `"APPEND"`): Apply the modern recipe for saddles.

### `["Spring to Life"]`
- `bushes` (boolean, current `false`): Allow Bushes to generate.
- `firefly_bushes` (boolean, current `false`): Allow Firefly Bushes to generate.
- `wildflowers` (boolean, current `false`): Allow Wildflowers to generate.
- `dry_grass` (boolean, current `false`): Allow Dry Grass to generate.
- `fallen_trees` (boolean, current `false`): Allow Fallen Trees to generate.
- `leaf_litter` (boolean, current `false`): Allow Leaf Litter to generate.
- `cactus_flowers` (boolean, current `false`): Allow Cactus Flowers to generate.
- `farm_animal_variants` (boolean, current `false`): Allow Chicken, Cow, and Pig variants to spawn.
- `wolf_sound_variants` (boolean, current `false`): Allow wolves to have sound variants.
- `camel_spawns` (boolean, current `false`): Allow Camels to spawn naturally.
- `spring_trades` (boolean, current `false`): Allow Wandering Traders to offer items from Spring to Life.
- `lodestone_loot` (boolean, current `false`): Allow Lodestones to generate in Ruined Portal loot chests.
- `mob_variants_spawn_chance` (float `0.0..1.0`, current `1.0`): Global spawn chance for mob variants; use datapacks for per-variant weighting.
- `cactus_flower_spawn_chance` (float `0.0..1.0`, current `0.25`): Chance for a cactus to generate with a Cactus Flower.
- `lodestone_recipe` (string: `"APPEND"`, `"REPLACE"`, or `"IGNORE"`, current `"APPEND"`): Apply the modern recipe for lodestones.

### `["Chase the Skies"]`
- `dried_ghasts` (boolean, current `false`): Allow Dried Ghasts to be obtainable through Nether Fossils and Piglin bartering.
- `leash_drop_connections` (boolean, current `true`): Drop leash connections when using a Firework Rocket boost.
- `tears_music_disc` (boolean, current `true`): Allow Ghasts to drop the Tears music disc.
- `happy_ghast_speed_modifier` (float `>= 0.0`, current `1.0`): Movement speed multiplier for ridden Happy Ghasts.
- `modern_leashes` (boolean, current `true`): Allow Leashes to have the modern physics and interactions.

### `["Hot as Lava"]`
- `lava_chicken_music_disc` (boolean, current `true`): Allow Chicken jockeys to drop the Lava Chicken music disc.

### `["Copper Age"]`
- `has_copper_horse_armor_loot` (boolean, current `true`): Allow Copper Horse Armor to generate in loot chests.
- `has_copper_golems` (boolean, current `true`): Allow Copper Golems to be built using a Carved Pumpkin.
- `golem_weathering_tick_from` (integer `> 0`, `<= golem_weathering_tick_to`, current `504000`): Minimum ticks before a Copper Golem advances to the next weathering stage.
- `golem_weathering_tick_to` (integer `> 0`, `>= golem_weathering_tick_from`, current `552000`): Maximum ticks before a Copper Golem advances to the next weathering stage.
- `golem_item_carry_amount` (integer `> 1`, current `16`): Maximum number of items a Copper Golem can carry.
- `has_copper_nuggets` (boolean, current `true`): Allow Copper Nuggets to be obtainable via crafting.
- `has_copper_toolset` (boolean, current `true`): Allow Copper Armor, Weapons, and Tools to be obtainable.
- `has_weathering_lightning_rods` (boolean, current `true`): Allow Weathering Lightning Rods to be obtainable.

### `["Mounts of Mayhem"]`
- `has_parched_skeletons` (boolean, current `false`): Allow Parched Skeletons to spawn naturally.
- `has_camel_husks` (boolean, current `false`): Allow Camel Husks to spawn naturally.
- `has_nautilus` (boolean, current `false`): Allow Nautilus to spawn naturally.
- `has_zombie_horses` (boolean, current `false`): Allow Zombie Horses to spawn naturally.
- `zombie_nautilus_spawn_chance` (float `0.0..1.0`, current `0.5`): Chance for a drowned to spawn riding a nautilus.
- `has_nautilus_armor_loot` (boolean, current `false`): Allow Nautilus Armor to generate in loot chests.
- `has_spears` (boolean, current `true`): Allow Spears to be obtainable and allow monsters to spawn holding them.
- `can_mounts_float_while_ridden` (boolean, current `true`): Allow mounts to float while ridden.

### `["Chaos Cubed"]`
- `has_sulfur_caves` (boolean, current `false`): Allow Sulfur Cave biomes to generate.
- `has_sulfur_springs` (boolean, current `false`): Allow Sulfur Springs to generate in Sulfur Caves.
- `do_geysers_erupt` (boolean, current `false`): Allow Potent Sulfur blocks to generate Geysers.
- `has_sulfur_cubes` (boolean, current `false`): Allow Sulfur Cubes to spawn in Sulfur Caves.
- `do_sulfur_cubes_explode` (boolean, current `true`): Allow explosive Sulfur Cube archetypes to explode.
- `do_sulfur_cubes_damage` (boolean, current `true`): Allow damaging Sulfur Cube archetypes to deal damage.
- `do_merchant_trade_chaos_cubed_contents` (boolean, current `false`): Allow Wandering Traders to offer items from Chaos Cubed.
- `has_bounce_music_disc` (boolean, current `false`): Allow the Bounce music disc to generate in Abandoned Mineshafts loot chests.

### `["Wilderness Bound"]`
- `has_dappled_forest` (boolean, current `false`): Allow Dappled Forest biomes to generate.

---

## 3. Mandatory Invariants

1. **Valid Forge TOML Structure & Strict Types:**
   - Keep all 11 TOML tables and every key present with strict types (booleans, integers, floats/numbers, or strings).
2. **Recipe Modes:**
   - `bundle_recipe`, `lead_recipe`, `saddle_recipe`, and `lodestone_recipe` must be `"APPEND"`, `"REPLACE"`, or `"IGNORE"`.
3. **24-bit RGB Color Bounds:**
   - `creaking_particle_color` and `creaking_particle_reverse_color` must be integers in `0..16777215` (`0x000000..0xFFFFFF`).
4. **Probability & Speed Bounds:**
   - `mob_variants_spawn_chance`, `cactus_flower_spawn_chance`, and `zombie_nautilus_spawn_chance` must be finite numbers in `0.0..1.0`.
   - `happy_ghast_speed_modifier` must be a finite number `>= 0.0`.
5. **Copper Age Golem Bounds:**
   - `golem_weathering_tick_from > 0`, `golem_weathering_tick_to > 0`, and `golem_weathering_tick_from <= golem_weathering_tick_to`.
   - `golem_item_carry_amount > 1`.
6. **Restart & Chunk-Generation Discipline:**
   - Restart the server after modifying `config/vanillabackport-common.toml`.
   - Worldgen toggles only affect newly generated chunks; existing chunks are unaffected.
7. **Excluded Runtime & World State:**
   - Never place runtime or world state (`logs/`, `world/`, `mods/`) or binary/log/secret artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/vanillabackport/configs/`.
