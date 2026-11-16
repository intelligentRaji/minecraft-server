---
name: farmersdelight-config
description: Inspect and configure Farmer's Delight common settings (trades, canvas signs, farming, crafting, vanilla item overrides, world generation, and tomato rope debug behavior) in mods/farmersdelight/configs/.
---

# Farmer's Delight Configuration Guide (`farmersdelight-config`)

Use this skill to inspect and modify **Farmer's Delight** (`modpack/server-client/FarmersDelight-1.20.1-1.3.4.jar`) configuration in `mods/farmersdelight/configs/`.

> **Startup / World-Load Forge TOML Config:** `config/farmersdelight-common.toml` is not live-reloadable via RCON; changes require a server restart to take effect. Additionally, changing shared gameplay, recipe, or stack-size settings (`enableVanillaCropCrates`, `enableStackableSoupItems`, `soupItemList`, `enableCookingPotRecipeBook`, or `enablePumpkinPieSneakToPlace`) requires matching client configs to prevent recipe/UI or stack-size desyncs.

---

## 1. Configuration File Overview (`mods/farmersdelight/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/farmersdelight-common.toml` | Forge common settings: villager/trader trades, rope reeling, canvas sign dark-background dyes, farming/rich soil/tomato vine ropes, crafting/cooking pot recipe book/crop crates/cutting board Fortune, vanilla overrides & soup stack sizes, world generation, and tomato rope permanence debug toggle. | TOML |

---

## 2. `config/farmersdelight-common.toml` Reference

### `[settings]`
- `enableFarmerFDTrades` (boolean, default `true`): Enables Novice and Apprentice Farmer villagers to buy crops from Farmer's Delight.
- `enableWanderingTraderFDTrades` (boolean, default `true`): Enables the Wandering Trader to sell seeds and plantables from Farmer's Delight.
- `enableRopeReeling` (boolean, default `true`): Allows players to reel back rope from bottom to top by sneak-using with an empty hand.
- `canvasSignDarkBackgroundList` (array of strings, default `["gray", "purple", "blue", "brown", "green", "red", "black"]`): Dye colors that default to white text when used as the background color of a Canvas Sign.
  - **Allowed values:** `"white"`, `"orange"`, `"magenta"`, `"light_blue"`, `"yellow"`, `"lime"`, `"pink"`, `"gray"`, `"light_gray"`, `"cyan"`, `"purple"`, `"blue"`, `"brown"`, `"green"`, `"red"`, `"black"`.

### `[farming]`
- `richSoilBoostChance` (float `0.0 ~ 1.0`, default `0.2`): Decimal probability that Rich Soil applies a bone meal boost to a crop planted on it. Set to `0.0` to disable.
- `enableTomatoVineClimbingTaggedRopes` (boolean, default `true`): Allows tomato crops to climb any rope tagged as `farmersdelight:ropes`. When `false`, restricts climbing to Farmer's Delight rope only. **Note:** When enabled, climbing converts tagged rope blocks into the block specified by `defaultTomatoVineRope`.
- `defaultTomatoVineRope` (string `namespace:path`, default `"farmersdelight:rope"`): Resource location of the rope block left behind when Tomato Vines are broken.

### `[crafting]`
- `enableCookingPotRecipeBook` (boolean, default `true`): Enables the Recipe Book button on the Cooking Pot GUI. *(Shared client/server UI setting.)*
- `enableVanillaCropCrates` (boolean, default `true`): Enables 3x3 storage crate recipes for vanilla crops. *(Shared client/server recipe setting.)*
- `cuttingBoardFortuneBonus` (float `0.0 ~ 1.0`, default `0.1`): Decimal percentage increase per Fortune level for obtaining rare results on the Cutting Board. Set to `0.0` to disable.

### `[overrides]`
- `enableVanillaSoupExtraEffects` (boolean, default `true`): Grants Nourishment when eating vanilla soups and stews.
- `enableRabbitStewJumpBoost` (boolean, default `true`): Grants Jump Boost when eating Rabbit Stew.
- `enablePumpkinPieSneakToPlace` (boolean, default `false`): Requires sneaking to place Pumpkin Pie down as a block. *(Shared client/server interaction setting.)*
- `enableCuttingBoardDispenserBehavior` (boolean, default `true`): Allows Dispensers to operate a Cutting Board in front of them using stored items as cutting tools.

### `[overrides.stack_size]`
- `enableStackableSoupItems` (boolean, default `true`): Makes any `BowlFoodItem` in `soupItemList` stackable to `16`. *(Shared client/server stack-size setting.)*
- `soupItemList` (array of `namespace:path` strings, default `["minecraft:mushroom_stew", "minecraft:beetroot_soup", "minecraft:rabbit_stew"]`): Target food items affected by `enableStackableSoupItems`. Every listed item **must** extend `BowlFoodItem` in code. *(Shared client/server stack-size setting.)*

### `[world]`
- `generateFDChestLoot` (boolean, default `true`): Adds Farmer's Delight loot pools (ropes, crops, tools, etc.) to chest loot tables.
- `generateVillageCompostHeaps` (boolean, default `true`): Generates Compost Heap structures in villages.
- `generateFDCropsOnVillageFarms` (boolean, default `true`): Allows Farmer's Delight crops to replace standard crops in village farm plots.

### `[debug]`
- `enableTomatoRopePermanence` (boolean, default `true`): Forces tomato crops hanging on rope to place a Rope block when broken. Due to technical limitations, this causes commands such as `/setblock` and world-editing tools to fail on the first attempt when replacing hanging tomato/rope blocks. Disable temporarily when editing regions in Creative or via commands; keep `true` for normal survival gameplay.

---

## 3. Mandatory Invariants

1. **Valid Forge TOML Types & Ranges:**
   - Keep `richSoilBoostChance` and `cuttingBoardFortuneBonus` within `0.0 ~ 1.0`.
   - Keep `canvasSignDarkBackgroundList` restricted to the 16 valid Minecraft dye color names.
   - Keep `defaultTomatoVineRope` and `soupItemList` entries as valid `namespace:path` resource locations (`soupItemList` items must extend `BowlFoodItem`).
2. **Restart & Client-Sync Discipline:**
   - `config/farmersdelight-common.toml` is loaded at startup/world-load and is not live-reloadable via RCON; restart the server after changes.
   - Keep client configurations aligned with the server whenever modifying `enableVanillaCropCrates`, `enableStackableSoupItems`, `soupItemList`, `enableCookingPotRecipeBook`, or `enablePumpkinPieSneakToPlace`.
3. **Excluded Runtime & World State:**
   - Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/farmersdelight/configs/`.
