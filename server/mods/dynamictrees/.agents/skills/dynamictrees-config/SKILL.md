---
name: dynamictrees-config
description: Inspect and configure Dynamic Trees common and server settings (vanilla replacement, recipes, seasonal integration, seed drops/planting, tree growth/harvesting, falling trees, interaction, worldgen, and debug markers) in mods/dynamictrees/configs/.
---

# Dynamic Trees Configuration Guide (`dynamictrees-config`)

Use this skill to inspect and modify **Dynamic Trees** (`modpack/server-client/DynamicTrees-1.20.1-1.4.11.jar`) configuration in `mods/dynamictrees/configs/`.

> **Startup / World-Load Forge TOML Configs:** Both `config/dynamictrees-common.toml` and `world/serverconfig/dynamictrees-server.toml` are loaded at server startup / world load and are not live-reloadable via RCON. Restart `mc-forge-server` after making changes.

---

## 1. Configuration File Overview (`mods/dynamictrees/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/dynamictrees-common.toml` | Forge common settings: vanilla sapling/fungi/village tree replacement, dirt bucket & mega seed recipes, biochar brewing base, and seasonal integration (Serene Seasons). | TOML |
| `world/serverconfig/dynamictrees-server.toml` | Forge server settings: falling tree leaf particle cap, seed drop/self-planting/TTL rates, tree growth/harvesting/hardness/rot/bone meal/swamp oaks, player interaction & falling tree damage, worldgen & dimension blacklist, and debug markers. | TOML |

---

## 2. `config/dynamictrees-common.toml` Reference

### `[vanilla]`
- `replaceVanillaSapling` (boolean, default `false`): When `true`, right-clicking with a vanilla sapling places a dynamic sapling instead.
- `replaceNyliumFungi` (boolean, default `true`): When `true`, Crimson Fungus and Warped Fungus that sprout from nylium grow into dynamic trees instead of vanilla fungi trees.
- `cancelVanillaVillageTrees` (boolean, default `true`): When `true`, cancels non-dynamic trees that spawn with vanilla villages.

### `[misc]`
- `generateDirtBucketRecipes` (boolean, default `true`): Automatically generates Dirt Bucket crafting recipes.
- `generateMegaSeedRecipe` (boolean, default `false`): Enables crafting seeds for mega species using four regular seeds.
- `biocharBrewingBase` (string, non-empty, default `"thick"`): Base potion used to brew Biochar Base (Minecraft potions typically use `"awkward"` or `"thick"`). If changed, update any corresponding Patchouli manual page if applicable.

### `[integration]`
- `preferredSeasonMod` (string, non-empty, default `"*"`): Mod ID of the preferred season mod for seasonal integration.
  - `"*"` accepts any available season integration (the first available).
  - `"!"` disables seasonal integration.
  - Or specify a concrete mod ID (e.g., `"sereneseasons"`).
- `enableSeasonalSeedDropFactor` (boolean, default `true`): Multiplies seed drop rates based on the current season (requires a season mod such as Serene Seasons).
- `enableSeasonalGrowthFactor` (boolean, default `true`): Multiplies tree growth rates based on the current season (requires a season mod such as Serene Seasons).
- `enableSeasonalFruitProductionFactor` (boolean, default `true`): Multiplies fruit production rates based on the current season (requires a season mod such as Serene Seasons).

---

## 3. `world/serverconfig/dynamictrees-server.toml` Reference

### Root Level
- `growthFolding` (integer `0 ~ 4096`, default `400`): Maximum number of leaf blocks that fling particles when a falling tree crashes into the ground. Higher values increase visual spectacle at the cost of client/server particle overhead. *(Note: This root-level key is distinct from `[trees].growthFolding`.)*

### `[seeds]`
- `leavesSeedDropRate` (float `0.0 ~ 64.0`, default `1.0`): Multiplier/rate at which seeds drop from leaves.
- `voluntarySeedDropRate` (float `0.0 ~ 1.0`, default `0.01`): Rate at which seeds voluntarily drop from branches.
- `seedPlantRate` (float `0.0 ~ 1.0`, default `0.1666666716337204`): Rate at which dropped seeds voluntarily plant themselves in their ideal biomes.
- `timeToLive` (integer `0 ~ 6000`, default `1200`): Ticks before a seed entity in the world attempts to plant itself or despawn (`1200` ticks = 1 minute).
- `seedOnlyForest` (boolean, default `true`): When `true`, seeds only voluntarily plant themselves in forest-like biomes.
- `seedMinForestness` (float `0.0 ~ 1.0`, default `0.0`): Minimum forestness required for non-forest-like biomes to allow voluntary seed planting (`0.0` = not a forest at all, `1.0` = effectively a forest).

### `[trees]`
- `growthMultiplier` (float `0.0 ~ 16.0`, default `0.5`): Factor multiplying the rate at which trees grow.
- `harvestMultiplier` (float `0.0 ~ 128.0`, default `1.0`): Factor multiplying the wood returned from harvesting a tree.
- `maxTreeHardness` (float `1.0 ~ 200.0`, default `20.0`): Maximum harvesting hardness that can be calculated, regardless of tree thickness.
- `treeHardnessMultiplier` (float `0.0078125 ~ 32.0`, default `1.0`): Multiplier for tree hardness. Higher values make trees slower to chop; lower values make them faster.
- `growthFolding` (integer `1 ~ 8`, default `2`): Performs `X` growth cycles at once while ignoring `(X - 1) / X` attempts. Higher values can improve performance, though very high values may cause irregular growth shapes.
- `dropSticks` (boolean, default `true`): Drops sticks for partial logs when harvesting.
- `scaleBiomeGrowthRate` (float `0.0 ~ 1.0`, default `0.5`): Scales growth by biome suitability (`0.5` is nominal; `0.0` means trees only grow in their native biome; `1.0` means trees grow anywhere as fast as in their native biome).
- `diseaseChance` (float `0.0 ~ 1.0`, default `0.0`): Chance of a tree on depleted soil to die (`1/256` ≈ `0.004` averages about 1 death per 16 Minecraft days; `0.0` disables soil-depletion death).
- `maxBranchRotRadius` (integer `0 ~ 24`, default `7`): Maximum radius of a branch allowed to rot away (`8` = full block size, `24` = full 3x3 thick size, `0` = disables rotting).
- `rootyBlockHardnessMultiplier` (float `0.0 ~ 128.0`, default `40.0`): How much harder it is to destroy a rooty soil block compared to its non-rooty state.
- `swampOaksInWater` (string enum, default `"ROOTED"`): Controls how oak trees generate in swamps.
  - **Allowed values:** `"ROOTED"` (shallow water with mangrove-like roots), `"SUNK"` (shallow water one block under the surface), `"DISABLED"` (swamp oaks will not generate on water).
- `boneMealGrowthPulses` (integer `1 ~ 512`, default `1`): Number of growth pulses sent when bone meal is applied to a tree (values above `64` are not recommended outside testing).

### `[interaction]`
- `isLeavesPassable` (boolean, default `false`): Makes all leaves passable (overridden if the Passable Foliage mod is installed).
- `vanillaLeavesCollision` (boolean, default `false`): When `true`, player movement on leaves is not enhanced.
- `enableBranchClimbling` (boolean, default `true`): Allows thinner branches to be climbed. *(Keep exact upstream key spelling `enableBranchClimbling`.)*
- `canopyCrash` (boolean, default `true`): Reduces fall damage on leaves at the expense of destroying the impacted leaf block(s).
- `axeDamageMode` (string enum, default `"THICKNESS"`): Damage dealt to the axe item when cutting down a tree.
  - **Allowed values:** `"VANILLA"` (standard 1 damage), `"THICKNESS"` (scaled by branch/trunk thickness), `"VOLUME"` (scaled by total tree volume).
- `enableFallingTrees` (boolean, default `true`): Trees fall over as a physics animation when harvested.
- `enableFallingTreeDamage` (boolean, default `true`): Falling trees harm living entities they hit.
- `fallingTreeDamageMultiplier` (float `0.0 ~ 100.0`, default `1.0`): Multiplier for damage dealt by a falling tree.
- `dirtBucketPlacesDirt` (boolean, default `true`): Allows the Dirt Bucket to place a dirt block on right-click.
- `sloppyBreakDrops` (boolean, default `false`): When `true`, improperly broken trees (not broken by an entity) still drop wood.
- `minRadiusForStrip` (integer `0 ~ 24`, default `6`): Minimum branch radius required before it can be stripped (`8` = full block size, `0` = disables stripping).
- `enableStripRadiusReduction` (boolean, default `true`): Stripping a branch decreases its radius by one.
- `canBoneMealFruit` (boolean, default `false`): Default for whether fruit growing on dynamic trees can be bone-mealed (can be overridden by individual fruit species).
- `canBoneMealPods` (boolean, default `true`): Default for whether pods growing on dynamic trees can be bone-mealed (can be overridden by individual pod species).
- `dynamicSaplingDrops` (boolean, default `true`): Dynamic sapling blocks drop their seed when broken.

### `[world]`
- `podzolGen` (boolean, default `true`): Randomly generates podzol under select trees such as spruce.
- `worldGen` (boolean, default `true`): World generation produces Dynamic Trees instead of vanilla trees.
- `dimensionsBlacklist` (array of non-empty strings, default `[]`): Blacklist of dimension registry names (e.g., `["minecraft:the_end", "twilightforest:twilight_forest"]`) where Dynamic Tree worldgen is disabled.

### `[debug]`
- `debug` (boolean, default `false`): Marks tree spawn locations with concrete circles (keep `false` for normal survival gameplay).

---

## 4. Common Configuration Tasks & Tuning Guidance

- **Adjusting Tree Growth Speed:**
  - Increase or decrease `[trees].growthMultiplier` (`0.0 ~ 16.0`, currently `0.5`).
  - To let trees grow at full speed outside their native biome, raise `[trees].scaleBiomeGrowthRate` toward `1.0`.
  - To make bone meal more impactful, increase `[trees].boneMealGrowthPulses` (keep `<= 64` for normal play).
- **Tuning Wood Yield & Chopping Effort:**
  - Adjust `[trees].harvestMultiplier` (`0.0 ~ 128.0`) to scale wood drops.
  - Adjust `[trees].treeHardnessMultiplier` and `[trees].maxTreeHardness` to change chopping time, and `[interaction].axeDamageMode` (`"VANILLA"`, `"THICKNESS"`, or `"VOLUME"`) to control axe durability cost.
- **Falling Trees & Player Safety:**
  - Disable `[interaction].enableFallingTreeDamage` (or lower `fallingTreeDamageMultiplier`) if falling trees are too lethal, or set `[interaction].enableFallingTrees = false` to disable falling tree physics altogether.
  - Lower root `growthFolding` (e.g., from `400` to `100`–`200`) if falling tree leaf particles cause client/server lag.
- **Seasonal Integration (Serene Seasons):**
  - Keep `[integration].preferredSeasonMod = "*"` (or set to `"sereneseasons"`) and toggle `enableSeasonalSeedDropFactor`, `enableSeasonalGrowthFactor`, and `enableSeasonalFruitProductionFactor` in `config/dynamictrees-common.toml`. Set `preferredSeasonMod = "!"` to disable seasonal integration completely.
- **Disabling Dynamic Tree Worldgen in Specific Dimensions:**
  - Add dimension registry IDs as non-empty strings to `[world].dimensionsBlacklist` in `world/serverconfig/dynamictrees-server.toml`.

---

## 5. Mandatory Invariants

1. **Valid Forge TOML Types, Keys & Ranges:**
   - Preserve exact section headers and key names (including `enableBranchClimbling`).
   - Keep `swampOaksInWater` within `{"ROOTED", "SUNK", "DISABLED"}` and `axeDamageMode` within `{"VANILLA", "THICKNESS", "VOLUME"}`.
   - Keep all numeric keys within their Forge-defined ranges and keep `biocharBrewingBase`, `preferredSeasonMod`, and all `dimensionsBlacklist` entries as non-empty strings.
2. **Restart Discipline:**
   - Restart `mc-forge-server` after any edit to `config/dynamictrees-common.toml` or `world/serverconfig/dynamictrees-server.toml` so changes take effect.
3. **Excluded Runtime & World State:**
   - Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/dynamictrees/configs/`.
