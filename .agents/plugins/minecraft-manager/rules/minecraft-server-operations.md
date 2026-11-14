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
