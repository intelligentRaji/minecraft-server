# Just Enough Items (`jei`) — Configuration Rules (`mods/jei/`)

## 1. Configuration Scope (`mods/jei/configs/`)
- Edit Just Enough Items (JEI) server configuration directly inside:
  - `mods/jei/configs/config/jei/server/world/default/jei-server.ini` (default server config template for newly generated worlds)
  - `mods/jei/configs/world/serverconfig/jei/jei-server.ini` (active per-world server configuration)
- For schema details, option descriptions, and operational notes, activate the [`jei-config` skill](file:///home/wakaria/dev/minecraft-server/mods/jei/.agents/skills/jei-config/SKILL.md).

## 2. Server Invariants
1. **Valid Schema & Structure (`jei-server.ini`):**
   - Both configuration files must follow the JEI `mezz_config` INI format.
   - The file must contain only the `[permissions]` section header.
   - Exactly 3 boolean keys (`"true"` or `"false"`) are permitted under `[permissions]`:
     - `enableCheatModeForOp`: boolean (`true` by default) — allows players with operator status (`/op`) to use JEI cheat mode.
     - `enableCheatModeForCreative`: boolean (`true` by default) — allows players in Creative Mode to use JEI cheat mode.
     - `enableCheatModeForGive`: boolean (`false` by default) — allows players with `/give` permission to use JEI cheat mode.
   - No unknown sections or extra keys are permitted.
2. **Cross-File Consistency:**
   - Both `mods/jei/configs/config/jei/server/world/default/jei-server.ini` and `mods/jei/configs/world/serverconfig/jei/jei-server.ini` must maintain identical `[permissions]` values so the server template and active world config never drift.
3. **Startup-Only Application & Restart Discipline:**
   - JEI server configurations are loaded during server initialization and world load; they are not hot-reloadable.
   - Any changes require restarting `mc-forge-server`. Before any restart, obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online.

## 3. Sanitized & Excluded Files
- Never place client-side JEI files (`jei-client.ini`, sort-order `.ini` files, `blacklist.cfg`), world backups (`world_backup_*`), runtime state directories (`logs/`, `mods/`, `playerdata/`, `region/`, `entities/`, `poi/`), symlinks, secrets, or binary/archive/database artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/jei/configs/`.
