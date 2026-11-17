# Botania — Configuration Rules (`mods/botania/`)

## 1. Configuration Scope (`mods/botania/configs/`)
- Edit Botania configuration directly inside `mods/botania/configs/`:
  - `config/botania-common.toml` — Forge common configuration covering mana animations, flower binding checks, Hand of Ender pickpocketing, Mana Enchanter, Relic system, Ring of Magnetization controls, block-breaking particles, mana spreader sound and raytrace prediction, Mana Lens harvest levels, Garden of Glass world/lexicon settings, and Rannuncarpus item/mod blacklists.
- For full section/key schemas, valid ranges, and operational notes, activate the [`botania-config` skill](file:///home/wakaria/dev/minecraft-server/mods/botania/.agents/skills/botania-config/SKILL.md).

## 2. Server Invariants
1. **Valid Forge TOML Syntax & Ranges:**
   - `[manaSpreaders].traceTime` must be an integer `>= 1` (default `400`).
   - `[harvestLevels].weightLens` and `[harvestLevels].boreLens` must be integers `>= 0` (defaults `2` and `3`).
   - `[gardenOfGlass].islandScaleMultiplier` must be an integer within `1 ~ 512` (default `8`); values below `4` (`< 1024` block spacing) risk Nether portal collisions in multiplayer Garden of Glass worlds.
   - `[rannuncarpus].itemBlacklist` entries must be valid `namespace:path` item registry strings, and `[rannuncarpus].modBlacklist` entries must be valid mod ID strings (keep `"storagedrawers"` excluded to prevent non-player block placement crashes).
2. **Startup / World-Load Config & Client Alignment:**
   - `botania-common.toml` is a startup/world-load Forge TOML config (not live-reloadable via RCON); changes require a server restart to take effect.
   - Disabling `manaEnchanter` or `relics` only disables new entries, creation, drops, and achievements—existing Mana Enchanters and Relics already in the world remain.
   - Keep shared gameplay settings (`manaEnchanter`, `relics`, `invertMagnetRing`, `harvestLevels`, `gardenOfGlass.spawnWithLexicon`) aligned with client configs when applicable to avoid progression or interaction discrepancies.

## 3. Excluded Files
- Do not include client-only (`botania-client.toml`) or per-world server (`botania-server.toml`) config files in `mods/botania/configs/`.
- Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/botania/configs/`.
