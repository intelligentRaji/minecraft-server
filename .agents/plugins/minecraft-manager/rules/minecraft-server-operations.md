---
trigger: always_on
description: Declarative invariants for Minecraft server operations, permissions, and chat formatting
---

# Minecraft Server Operations & Plugin Architecture

### Zero-Downtime & Restart Discipline
- **Live Changes First:** Never restart or stop `mc-forge-server` for live-capable changes (LuckPerms groups/permissions, scoreboard teams, `op`/`deop`, gamerules, or whitelist updates).
- **When Restarts Are Valid:** Only restart `mc` when server mods (`modpack/server-only/` or `modpack/server-client/` synced to `./data/mods/`) or startup-only configs (`server.properties`, `docker-compose.yml`, non-reloadable mod configs) change.

### Disruptive Action Guardrails
- **Explicit Confirmation:** Obtain user confirmation before running `stop`, `kick`, `ban`, `whitelist off`, or restarting/stopping `mc-forge-server`.
- **Pre-Check:** When players may be online, check `list` and run `save-all` via `minecraft-rcon` before any planned container restart.

### Skill & Script Decoupling
- **Single-Domain Scripts:** Keep each skill's scripts focused strictly on its own domain (e.g., data lookup or single-purpose execution).
- **Skill Handoffs Over Imports:** Never import Python functions across different skills; skills must hand off to one another by activating the target skill (e.g., `minecraft-role-manager` $\rightarrow$ `minecraft-rcon`).

### Permissions, Chat & Clan Tag Invariants
- **LuckPerms as Single Source of Truth:** `internalPermissionsEnable` in `data/config/paradigm/main.json` must remain `false` so Paradigm resolves permissions and `{prefix}` / `{suffix}` metadata from LuckPerms rather than its internal SQLite `paradigm.db`.
- **Base Player Permissions on `group.default`:** Because `internalPermissionsEnable` is `false`, `group.default` in LuckPerms (inherited by all players and `moderator`) must retain the 19 default Paradigm player nodes (`paradigm.msg`, `paradigm.reply`, `paradigm.mention.player`, `paradigm.spawn`, `paradigm.seen`, `paradigm.ignore`, `paradigm.home`, `paradigm.sethome`, `paradigm.delhome`, `paradigm.homes`, `paradigm.back`, `paradigm.tpa`, `paradigm.tpahere`, `paradigm.tpaccept`, `paradigm.tpdeny`, `paradigm.tpcancel`, `paradigm.warp`, `paradigm.warps`, and `paradigm.warp.info`).
- **Uniform Prefix, Name & Suffix Coloring:** LuckPerms staff prefixes must end with an active trailing color code and no trailing `&r` (`&c&l[OWN] `, `&c[ADM] `, `&d[MOD] `) so Paradigm's `{prefix}{player_name}{suffix}` format in `data/config/paradigm/chat.json` and `data/config/paradigm/tablist.json` colors the prefix, nickname, and clan suffix uniformly.
- **Clan Suffix Reservation:** FCM Clans manages user suffixes at priority `100` (`lp user <uuid> meta setsuffix 100 "<tag>"`). Never overwrite or clear user suffixes when modifying roles or permissions.
