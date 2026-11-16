# Farmer's Delight — Configuration Rules (`mods/farmersdelight/`)

## 1. Configuration Scope (`mods/farmersdelight/configs/`)
- Edit Farmer's Delight configuration directly inside `mods/farmersdelight/configs/`:
  - `config/farmersdelight-common.toml` — Forge common configuration covering villager/trader trades, rope reeling, canvas sign dark-background dyes, farming/rich soil/tomato vine ropes, crafting/recipe book/cutting board Fortune bonus, vanilla soup & pumpkin pie & dispenser overrides, world generation loot/villages, and tomato rope permanence debug behavior.
- For full section/key schemas, valid ranges, and operational notes, activate the [`farmersdelight-config` skill](file:///home/wakaria/dev/minecraft-server/mods/farmersdelight/.agents/skills/farmersdelight-config/SKILL.md).

## 2. Server Invariants
1. **Valid Forge TOML Syntax & Ranges:**
   - `richSoilBoostChance` and `cuttingBoardFortuneBonus` must be floats within `0.0 ~ 1.0`.
   - `canvasSignDarkBackgroundList` must only contain valid Minecraft dye color names (`white`, `orange`, `magenta`, `light_blue`, `yellow`, `lime`, `pink`, `gray`, `light_gray`, `cyan`, `purple`, `blue`, `brown`, `green`, `red`, `black`).
   - `defaultTomatoVineRope` and entries in `soupItemList` must be valid `namespace:path` resource locations (`soupItemList` entries must extend `BowlFoodItem`).
2. **Startup / World-Load Config & Client Sync:**
   - `farmersdelight-common.toml` is a startup/world-load config (not live-reloadable via RCON); changes require a server restart to take effect.
   - If shared gameplay, recipe, or stack-size settings change (`enableVanillaCropCrates`, `enableStackableSoupItems`, `soupItemList`, `enableCookingPotRecipeBook`, or `enablePumpkinPieSneakToPlace`), client configs must match the server to avoid recipe/UI or stack-size desyncs.

## 3. Sanitized & Excluded Files
- Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/farmersdelight/configs/`.
