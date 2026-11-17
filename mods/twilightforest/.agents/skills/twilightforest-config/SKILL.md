---
name: twilightforest-config
description: Inspect and configure Twilight Forest common settings (portals, Keepsake Casket locking, skull candles, boss drop chests, cloud precipitation, dimension spawn settings, Uncrafting Table, Magic Trees, and Shield Parrying) in mods/twilightforest/configs/.
---

# Twilight Forest Configuration Guide (`twilightforest-config`)

Use this skill to inspect and modify **The Twilight Forest** (`modpack/server-client/twilightforest-1.20.1-4.3.2508-universal.jar`) configuration in `mods/twilightforest/configs/`.

> **Startup / World-Load Forge TOML Config:** `config/twilightforest-common.toml` is not live-reloadable via RCON; changes require a server restart to take effect.

---

## 1. Configuration File Overview (`mods/twilightforest/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/twilightforest-common.toml` | Forge common settings: portal creation and advancement gating, Keepsake Casket `uuid_locking`, Skull Candles, creative item enchantments, boss drop chests, cloud precipitation distance, new-player dimension spawn settings, Uncrafting Table multipliers/lists/toggles, Magic Trees core toggles/ranges, and Shield Parrying. | TOML |

---

## 2. `config/twilightforest-common.toml` Reference

### Top-Level Portal & Dimension Rules
- `originDimension` (string, default `"minecraft:overworld"`): Dimension (`namespace:path`) from which players can always travel to the Twilight Forest and to which return portals send players.
- `allowPortalsInOtherDimensions` (boolean, default `false`): Allows Twilight Forest portals to be created outside `originDimension`.
- `adminOnlyPortals` (boolean, default `false`): Restricts portal creation to server operators (admins) and limits portal formation scanning to near ops only.
- `disablePortalCreation` (boolean, default `false`): Disables Twilight Forest portal creation entirely.
- `checkPortalDestination` (boolean, default `false`): Pre-checks new portal destinations for safety; if enabled, portals fail to form rather than redirecting to a safe alternate destination (also reduces portal formation check rate).
- `portalLightning` (boolean, default `false`): When `true`, lightning that activates a portal will not set nearby blocks on fire.
- `shouldReturnPortalBeUsable` (boolean, default `true`): When `false`, return portals require the activation item to be usable.
- `portalUnlockedByAdvancement` (string, default `""`): Valid advancement resource location (`namespace:path`, e.g. `"minecraft:story/mine_diamond"`) required to unlock portal creation. Empty `""` leaves the portal unlocked.
- `maxPortalSize` (integer `>= 4`, default `64`): Maximum number of water spaces checked when creating a portal. Very high values may cause performance issues.

### Top-Level Gameplay & World Settings
- `uuid_locking` (boolean, default `false`): When `true`, Keepsake Caskets spawned on player death are locked to the owner's UUID (server operators can still open locked caskets).
- `skull_candles` (boolean, default `false`): When `true`, disables creating Skull Candles by right-clicking a vanilla skull with a candle (useful for resolving mod conflicts).
- `default_item_enchantments` (boolean, default `true`): When `false`, items that come enchanted when crafted (such as ironwood or steeleaf gear) do not display those enchantments in the creative inventory. Does not alter crafting recipes themselves (use a datapack for recipe changes).
- `boss_drop_chests` (boolean, default `true`): When `true`, Twilight Forest bosses place their drops in a chest at their original spawn location instead of dropping loot directly (Knight Phantoms are unaffected).
- `cloudBlockPrecipitationDistance` (integer `>= 0`, default `32`): Number of blocks downward from a cloud block checked for weather/precipitation logic. Lower to improve tick rate, or set to `0` to disable cloud precipitation logic entirely.

### `["Dimension Settings"]`
> **Irreversible Consequences:** These settings affect initial player spawning and return portals and cannot be reversed without world/player consequences.
- `newPlayersSpawnInTF` (boolean, default `false`): When `true`, players joining for the first time spawn directly in the Twilight Forest.
- `portalForNewPlayer` (boolean, default `false`): When `true`, spawns a return portal for new players sent to the Twilight Forest when `newPlayersSpawnInTF` is enabled.

### `["Uncrafting Table"]`
- `uncraftingXpCostMultiplier` (float `>= 0.0`, default `1.0`): Multiplier applied to the total XP cost of uncrafting an item (rounded up). Set to `0.0` to remove XP cost for reversed crafting recipes (special uncrafting recipes retain their normal cost).
- `repairingXpCostMultiplier` (float `>= 0.0`, default `1.0`): Multiplier applied to the total XP cost of repairing an item (rounded up). Set to `0.0` to remove repairing XP cost.
- `disableUncraftingRecipes` (array of strings, default `["twilightforest:giant_log_to_oak_planks"]`): Recipe IDs (`namespace:path`) disabled from uncrafting. To ban all recipes for an item or block an ingredient, use the `twilightforest:banned_uncraftables` or `twilightforest:banned_uncrafting_ingredients` item tags via datapack.
- `flipRecipeList` (boolean, default `false`): When `true`, inverts `disableUncraftingRecipes` from a blacklist to a whitelist.
- `blacklistedUncraftingModIds` (array of strings, default `[]`): Mod IDs whose recipes are completely disabled from uncrafting (e.g. `"twilightforest"`).
- `flipIdList` (boolean, default `false`): When `true`, inverts `blacklistedUncraftingModIds` from a blacklist to a whitelist.
- `enableShapelessCrafting` (boolean, default `false`): When `true`, allows the Uncrafting Table to uncraft shapeless recipes in addition to shaped recipes.
- `disableUncrafting` (boolean, default `false`): Disables reversing normal crafting recipes in the Uncrafting Table while keeping special uncrafting recipes active.
- `disableUncraftingTable` (boolean, default `false`): Disables all usage of the Uncrafting Table and prevents it from appearing in loot or being crafted. Prefer `disableUncrafting` if you only want to block normal recipe reversal.

### `["Magic Trees"]`
- `disableTimeCore` (boolean, default `false`): When `true`, disables the Timewood Core.
- `timeCoreRange` (integer `1..128`, default `16`): Effect radius in blocks for the Timewood Core.
- `disableTransformationCore` (boolean, default `false`): When `true`, disables the Transformation Core.
- `transformationCoreRange` (integer `1..128`, default `16`): Effect radius in blocks for the Transformation Core.
- `disableMiningCore` (boolean, default `false`): When `true`, disables the Minewood Core.
- `miningCoreRange` (integer `1..128`, default `16`): Effect radius in blocks for the Minewood Core.
- `disableSortingCore` (boolean, default `false`): When `true`, disables the Sortingwood Core.
- `sortingCoreRange` (integer `1..128`, default `16`): Effect radius in blocks for the Sortingwood Core.

### `["Shield Parrying"]`
- `parryNonTwilightAttacks` (boolean, default `false`): When `true`, allows parrying non-Twilight Forest projectiles.
- `shieldParryTicksArrow` (integer `>= 0`, default `40`): Number of ticks after raising a shield during which a projectile can be parried.

---

## 3. Mandatory Invariants

1. **Exact Root Schema (18 Root Keys):**
   - Preserve all 14 top-level keys and all 4 TOML tables (`["Dimension Settings"]`, `["Uncrafting Table"]`, `["Magic Trees"]`, `["Shield Parrying"]`) in `config/twilightforest-common.toml`.
2. **Valid Resource Locations, Lists & Ranges:**
   - Keep `originDimension` as a valid `namespace:path` string, and keep any non-empty `portalUnlockedByAdvancement` as a valid `namespace:path` advancement ID.
   - Keep `maxPortalSize >= 4`, `cloudBlockPrecipitationDistance >= 0`, `uncraftingXpCostMultiplier >= 0.0`, `repairingXpCostMultiplier >= 0.0`, all four Magic Trees core ranges within `1..128`, and `shieldParryTicksArrow >= 0`.
   - Keep every entry in `disableUncraftingRecipes` and `blacklistedUncraftingModIds` as a non-empty string.
3. **Restart Discipline:**
   - `config/twilightforest-common.toml` is loaded at startup/world-load and is not live-reloadable via RCON; restart the server after changes.
4. **Excluded Files & Runtime State:**
   - Do not include `twilightforest-client.toml` or `twilightforest-server.toml` in `mods/twilightforest/configs/`.
   - Never place runtime or world state (`world/`, `logs/`, `mods/`) or secrets, databases, or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/twilightforest/configs/`.
