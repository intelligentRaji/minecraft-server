---
name: minecraft-rcon
description: >-
  Execute live Minecraft server commands against mc-forge-server via RCON
  (rcon-cli), including batched commands, server inspection, and LuckPerms
  administration.
---

# Minecraft RCON Runbook

Shared procedure and helper script for running live server commands on the Docker Forge 1.20.1 server (`mc-forge-server`) via `rcon-cli`.

---

## Quick Usage

Ensure `mc-forge-server` is running (`docker compose ps`), then use [rcon.py](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/skills/minecraft-rcon/scripts/rcon.py):

```bash
# Preview without executing:
python3 .agents/plugins/minecraft-manager/skills/minecraft-rcon/scripts/rcon.py --dry-run "list"

# Run a single command:
python3 .agents/plugins/minecraft-manager/skills/minecraft-rcon/scripts/rcon.py "list"

# Batch multiple commands in a single docker exec call:
python3 .agents/plugins/minecraft-manager/skills/minecraft-rcon/scripts/rcon.py "save-all" "say Server saved!"
```

---

## Common Server Commands

| Task | Command |
| :--- | :--- |
| Check online players | `list` |
| Broadcast message | `say <message>` |
| Force world save | `save-all` |
| Set time / weather | `time set day`, `weather clear` |
| Whitelist management | `whitelist add <player>`, `whitelist remove <player>`, `whitelist list` |
| LuckPerms group permission | `lp group <group> permission set <node> true` |
| LuckPerms user group | `lp user <uuid_or_name> parent set <group>` |

---

## Operational Notes & Gotchas

- **LuckPerms stdout on Forge 1.20.1:** `lp` commands execute asynchronously and return empty stdout over `rcon-cli`. To verify LuckPerms state, run `lp export <name>` and inspect `data/config/luckperms/<name>.json.gz` (and remove the temporary export afterward).
- **Offline-mode player UUIDs:** Because the server runs in offline mode, LuckPerms cannot look up Mojang UUIDs for players who have not joined since LuckPerms was installed. Resolve the player's UUID from [usercache.json](file:///home/wakaria/dev/minecraft-server/data/usercache.json) when targeting offline players.
- **Connection refused on port `25575`:** If `mc-forge-server` just restarted, wait for `docker compose ps` to report `healthy` before retrying RCON.
- **Safety guardrails:** Confirm with the user before running disruptive commands (`stop`, `kick`, `ban`, `pardon`, `whitelist off`, `difficulty`, or `gamerule` changes).
