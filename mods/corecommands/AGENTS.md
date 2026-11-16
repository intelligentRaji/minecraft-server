# Core Commands — Configuration Rules (`mods/corecommands/`)

## 1. Configuration Scope (`mods/corecommands/configs/`)
- Edit Core Commands static configuration directly inside `mods/corecommands/configs/` (`config.json` and `rules.json`).
- For schema details, operational notes, and invariants, activate the [`corecommands-config` skill](file:///home/wakaria/dev/minecraft-server/mods/corecommands/.agents/skills/corecommands-config/SKILL.md).

## 2. Server Invariants
1. **Valid Schema & Types (`config.json`):**
   - JSON object containing only `backCommandEnabled` (boolean, currently `true`) and optional/descriptive `comment_backCommand` (string).
2. **Valid Schema & Types (`rules.json`):**
   - JSON array of non-empty strings representing server rules shown by `/rules`.
3. **Live Commands vs. Startup Config:**
   - Manage warps, spawn, homes, TPA requests, and AFK status via live in-game/RCON commands (`/setwarp`, `/delwarp`, `/setspawn`, `/sethome`, `/tpa`, `/afk`) rather than editing runtime state files.
   - Changes to `mods/corecommands/configs/config.json` or `mods/corecommands/configs/rules.json` require a server restart (or mod reload if supported).

## 3. Sanitized & Excluded Files
- Never place runtime player/world state files (`afkstatus.json`, `deathlocation.json`, `homes.json`, `lastlocation.json`, `lastmessagerecipient.json`, `logoutposition.json`, `playerjoinstatus.json`, `spawn.json`, `tparequests.json`, `warps.json`) or binary/log/archive artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar`, `*.gz`, `*.tgz`, `*.bak`) inside `mods/corecommands/configs/`.
