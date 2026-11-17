# Twilight Forest — Configuration Rules (`mods/twilightforest/`)

## 1. Configuration Scope (`mods/twilightforest/configs/`)
- Edit Twilight Forest configuration directly inside `mods/twilightforest/configs/`:
  - `config/twilightforest-common.toml` — Forge common configuration covering portal & dimension rules, Keepsake Casket UUID locking, Skull Candles, default item enchantments, boss drop chests, cloud block precipitation distance, Dimension Settings, Uncrafting Table rules, Magic Trees cores, and Shield Parrying.
- For full section/key schemas, valid ranges, and operational notes, activate the [`twilightforest-config` skill](file:///home/wakaria/dev/minecraft-server/mods/twilightforest/.agents/skills/twilightforest-config/SKILL.md).

## 2. Server Invariants
1. **Exact Root Schema (18 Root Keys):**
   - `config/twilightforest-common.toml` must preserve the exact 18 root keys: 14 top-level keys (`originDimension`, `allowPortalsInOtherDimensions`, `adminOnlyPortals`, `disablePortalCreation`, `checkPortalDestination`, `portalLightning`, `shouldReturnPortalBeUsable`, `portalUnlockedByAdvancement`, `maxPortalSize`, `uuid_locking`, `skull_candles`, `default_item_enchantments`, `boss_drop_chests`, `cloudBlockPrecipitationDistance`) plus 4 TOML tables (`["Dimension Settings"]`, `["Uncrafting Table"]`, `["Magic Trees"]`, and `["Shield Parrying"]`).
2. **Valid Resource Locations, Lists & Ranges:**
   - `originDimension` must be a valid `namespace:path` resource location string (default `"minecraft:overworld"`).
   - `portalUnlockedByAdvancement`, when non-empty, must be a valid `namespace:path` advancement resource location string (empty `""` leaves the portal unlocked).
   - `maxPortalSize` must be an integer `>= 4` (default `64`).
   - `cloudBlockPrecipitationDistance` must be an integer `>= 0` (default `32`; `0` disables cloud precipitation logic).
   - `["Uncrafting Table"].uncraftingXpCostMultiplier` and `repairingXpCostMultiplier` must be numbers `>= 0.0` (defaults `1.0`).
   - `["Uncrafting Table"].disableUncraftingRecipes` and `blacklistedUncraftingModIds` must contain only non-empty strings.
   - `["Magic Trees"]` core ranges (`timeCoreRange`, `transformationCoreRange`, `miningCoreRange`, `sortingCoreRange`) must be integers within `1..128` (default `16`).
   - `["Shield Parrying"].shieldParryTicksArrow` must be an integer `>= 0` (default `40`).
3. **Startup / World-Load Config & Client Alignment:**
   - `twilightforest-common.toml` is a startup/world-load Forge TOML config (not live-reloadable via RCON); changes require a server restart to take effect.
   - `["Dimension Settings"]` (`newPlayersSpawnInTF`, `portalForNewPlayer`) are not reversible without world/player spawn consequences.

## 3. Excluded Files
- Do not include client-only (`twilightforest-client.toml`) or per-world server (`twilightforest-server.toml`) config files in `mods/twilightforest/configs/`.
- Never place runtime or world state (`world/`, `logs/`, `mods/`) or secrets, databases, or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/twilightforest/configs/`.
