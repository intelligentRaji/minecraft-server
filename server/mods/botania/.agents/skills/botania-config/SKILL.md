---
name: botania-config
description: Inspect and configure Botania common settings (animations, flower binding, Hand of Ender, Mana Enchanter, Relics, Magnet Ring, particles, mana spreaders, lens harvest levels, Garden of Glass, and Rannuncarpus blacklists) in mods/botania/configs/.
---

# Botania Configuration Guide (`botania-config`)

Use this skill to inspect and modify **Botania** (`modpack/server-client/Botania-1.20.1-456-FORGE.jar`) configuration in `mods/botania/configs/`.

> **Startup / World-Load Forge TOML Config:** `config/botania-common.toml` is not live-reloadable via RCON; changes require a server restart to take effect.

---

## 1. Configuration File Overview (`mods/botania/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/botania-common.toml` | Forge common settings: mana pool charge animations, flower binding checks, Hand of Ender pickpocketing, Mana Enchanter, Relics, Ring of Magnetization inversion, block-breaking particles, mana spreader sound & trace ticks, lens harvest levels, Garden of Glass spacing/lexicon, and Rannuncarpus item/mod blacklists. | TOML |

---

## 2. `config/botania-common.toml` Reference

### Top-Level Settings
- `chargeAnimation` (boolean, default `true`): Enables the animation when an item is charging on top of a Mana Pool. Set to `false` to disable.
- `flowerBindingForceCheck` (boolean, default `true`): Toggles strict checking when flowers connect to Mana Pools or Mana Spreaders. Turn off **only** on extremely large worlds with an exaggerated count of spreaders/pools experiencing TPS lag.
- `enderPickpocket` (boolean, default `true`): Allows the Hand of Ender to pickpocket other players' Ender Chests. Set to `false` to disable.
- `manaEnchanter` (boolean, default `true`): Enables the Mana Enchanter. Setting to `false` only disables the Lexica Botania entry and creation; existing Mana Enchanters already in the world remain.
- `relics` (boolean, default `true`): Enables the Relic system. Setting to `false` only disables entries, drops, and achievements; existing Relics already in the world remain.
- `invertMagnetRing` (boolean, default `false`): Inverts the Ring of Magnetization's controls from sneak-to-stop to sneak-to-work when set to `true`.

### `[blockBreakingParticles]`
- `enabled` (boolean, default `true`): Enables block-breaking particles from Botania flowers and items. Set to `false` to disable.
- `toolEnabled` (boolean, default `true`): Enables block-breaking particles from the Terra Shatterer (which can produce many particles at higher levels). Set to `false` to disable.

### `[manaSpreaders]`
- `silent` (boolean, default `false`): Set to `true` to disable the mana spreader shooting sound.
- `traceTime` (integer `>= 1`, default `400`): Number of ticks into the future that mana spreaders predict where mana bursts go. Lowering this improves spreader performance, but prevents spreaders from firing at targets that are too far away.

### `[harvestLevels]`
- `weightLens` (integer `>= 0`, default `2`): Harvest level of the Mana Lens: Weight (`2` = iron level, `3` = diamond level).
- `boreLens` (integer `>= 0`, default `3`): Harvest level of the Mana Lens: Bore (`3` = diamond level).

### `[gardenOfGlass]`
- `spawnWithLexicon` (boolean, default `true`): Spawns players with a Lexica Botania in Garden of Glass worlds. Set to `false` if pack progression does not start with Botania.
- `islandScaleMultiplier` (integer `1 ~ 512`, default `8`): Multiplier for island distances in multiplayer Garden of Glass worlds. Islands are placed on a 256-block grid (spawn island at `256, 256`); default scale `8` spaces islands `2048` blocks apart. **Warning:** Values below `4` (`< 1024` block spacing) are not recommended due to Nether portal collisions.

### `[rannuncarpus]`
- `itemBlacklist` (array of strings, default `[]`): List of item registry names (`"namespace:path"`) ignored by Rannuncarpuses when placing blocks.
- `modBlacklist` (array of strings, default `["storagedrawers"]`): List of mod IDs ignored by Rannuncarpuses. Ignores `"storagedrawers"` by default due to crashes when placing drawer blocks without player involvement.

---

## 3. Mandatory Invariants

1. **Valid Forge TOML Types & Ranges:**
   - Keep `traceTime` as an integer `>= 1`.
   - Keep `weightLens` and `boreLens` as integers `>= 0`.
   - Keep `islandScaleMultiplier` within `1 ~ 512` (avoid values `< 4` in multiplayer Garden of Glass worlds to prevent Nether portal collisions).
   - Keep `itemBlacklist` entries as valid `namespace:path` item registry strings and `modBlacklist` entries as valid mod ID strings (keep `"storagedrawers"` in `modBlacklist` unless Storage Drawers is absent or verified safe).
2. **Restart Discipline:**
   - `config/botania-common.toml` is loaded at startup/world-load and is not live-reloadable via RCON; restart the server after changes.
3. **Excluded Files & Runtime State:**
   - Do not include `botania-client.toml` or `botania-server.toml` in `mods/botania/configs/`.
   - Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/botania/configs/`.
