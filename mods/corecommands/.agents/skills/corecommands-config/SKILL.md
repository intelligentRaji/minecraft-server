---
name: corecommands-config
description: Inspect and configure Core Commands static settings (/back command toggle and /rules list) in mods/corecommands/configs/.
---

# Core Commands Configuration Guide (`corecommands-config`)

Use this skill to inspect and modify **Core Commands** (`corecommands-2.0.1.jar`) static configuration in `mods/corecommands/configs/`.

> **Restart & Live Operations:** `mods/corecommands/configs/config.json` and `mods/corecommands/configs/rules.json` are startup-loaded, so changes require a server restart (or mod reload if supported). Runtime features such as warps, spawn, homes, TPA requests, and AFK status are managed live via in-game/RCON commands (`/setwarp`, `/delwarp`, `/setspawn`, `/sethome`, `/tpa`, `/afk`) rather than editing runtime state files.

---

## 1. Configuration Files Overview (`mods/corecommands/configs/`)

| File | Purpose & Key Settings | Format |
| :--- | :--- | :--- |
| `config.json` | Core behavior toggles (enabling/disabling `/back`). | JSON |
| `rules.json` | Ordered list of server rules displayed by `/rules`. | JSON |

---

## 2. `config.json` Reference

JSON object containing only the following keys:

- `backCommandEnabled` (boolean, currently `true`): Enables or disables the `/back` command for players.
- `comment_backCommand` (string, optional/descriptive, currently `"Set to false to disable the /back command"`): Descriptive comment explaining the `backCommandEnabled` toggle.

---

## 3. `rules.json` Reference

JSON array of non-empty strings representing the server rules printed when a player runs `/rules`.

Current entries:
1. `"1. Be respectful."`
2. `"2. No griefing."`
3. `"3. No spamming."`
4. `"4. Follow admin instructions."`
5. `"5. No hacking or exploiting."`

---

## 4. Mandatory Server Invariants

1. **Valid JSON & Field Types (`config.json`):**
   - Must be a JSON object containing only `backCommandEnabled` (JSON boolean: `true` or `false`) and optional/descriptive `comment_backCommand` (JSON string).
2. **Valid JSON & Element Types (`rules.json`):**
   - Must be a JSON array where every element is a non-empty string.
3. **Excluded Runtime State:**
   - Never place runtime player/world state files (`afkstatus.json`, `deathlocation.json`, `homes.json`, `lastlocation.json`, `lastmessagerecipient.json`, `logoutposition.json`, `playerjoinstatus.json`, `spawn.json`, `tparequests.json`, `warps.json`) or binary/log/archive artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar`, `*.gz`, `*.tgz`, `*.bak`) inside `mods/corecommands/configs/`.
