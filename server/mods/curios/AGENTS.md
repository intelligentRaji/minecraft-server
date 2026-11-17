# Curios — Configuration Rules (`mods/curios/`)

## 1. Configuration Scope (`mods/curios/configs/`)
- Edit Curios configuration directly inside `mods/curios/configs/`:
  - `config/curios-common.toml` — Forge common configuration defining custom or modified Curios slot definitions (`slots`).
  - `world/serverconfig/curios-server.toml` — Forge server/world configuration controlling death-retention behavior (`keepCurios`) and Curios menu layout (`[menu]` and `[menu.experimental]`).
- For full section/key schemas, valid ranges, and operational notes, activate the [`curios-config` skill](file:///home/wakaria/dev/minecraft-server/mods/curios/.agents/skills/curios-config/SKILL.md).

## 2. Server Invariants
1. **Valid Forge TOML Syntax, Enums & Ranges:**
   - `slots` in `config/curios-common.toml` must be a TOML array of strings following the Curios slot configuration syntax (`https://docs.illusivesoulworks.com/curios/configuration#slot-configuration`).
   - `keepCurios` in `world/serverconfig/curios-server.toml` must be one of `"ON"`, `"DEFAULT"`, or `"OFF"`.
   - `[menu].enableLegacyMenu` must be a boolean (`true` or `false`).
   - `[menu.experimental].minimumColumns` must be an integer within `1 ~ 8`.
   - `[menu.experimental].maxSlotsPerPage` must be an integer within `1 ~ 48`.
2. **Startup / World-Load Config & Client Alignment:**
   - `curios-common.toml` and `curios-server.toml` are loaded at startup/world-load (not live-reloadable via RCON); changes require a server restart to take effect.
   - If `slots` in `curios-common.toml` is modified, keep client configs aligned with the server to avoid slot/UI desyncs.

## 3. Sanitized & Excluded Files
- Never place per-player curio inventories/tags (`data/world/playerdata/`), world/runtime state (`data/world/`, `data/logs/`, `data/mods/`), or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/curios/configs/`.
