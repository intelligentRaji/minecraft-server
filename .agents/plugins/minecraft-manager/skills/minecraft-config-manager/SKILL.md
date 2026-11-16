---
name: minecraft-config-manager
description: >-
  Inspect, modify, and reload Minecraft Forge 1.20.1 server, mod, and world
  configurations in data/ while enforcing zero-downtime reload rules and
  persisting changes via minecraft-config-sync.
---

# Minecraft Configuration Management Runbook

Step-by-step procedure for inspecting, editing, validating, and applying Minecraft Forge 1.20.1 server, mod, and world configurations on `mc-forge-server`.

---

### Step 1: Locate Target Configuration Scope
Edit the appropriate runtime source depending on what setting is changing:

- **Core server properties (`server.properties` keys):** Edit environment variables in [docker-compose.yml](file:///home/wakaria/dev/minecraft-server/docker-compose.yml) or `.env` (`itzg/minecraft-server` regenerates `data/server.properties` on startup—do not edit `data/server.properties` directly or track it in Git).
- **Global mod & plugin configs:** `data/config/` (for example `data/config/paradigm/*.json`, `data/config/DistantHorizons.toml`, `data/config/simplebackups-common.toml`).
- **World-scoped server configs & templates:** `data/world/serverconfig/*.toml` (for example `forge-server.toml`, `create-server.toml`, `simplebackups-server.toml`) and world-creation templates in `data/defaultconfigs/`.
- **JVM flags:** `data/user_jvm_args.txt`.

---

### Step 2: Enforce Configuration Invariants
Before modifying Paradigm Essentials or Forge permissions configs, verify all invariants in [minecraft-server-operations.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/rules/minecraft-server-operations.md):

- `data/config/paradigm/main.json` must keep `"internalPermissionsEnable"` set to `false`.
- `data/world/serverconfig/forge-server.toml` must keep `permissionHandler = "luckperms:permission_handler"`.
- `data/config/paradigm/chat.json` and `data/config/paradigm/tablist.json` must preserve `{prefix}{player_name}{suffix}` formatting.

---

### Step 3: Apply Configuration Changes (Live Reload vs. Planned Restart)
- **Live-reloadable configs (Zero-Downtime First):**
  Activate the **`minecraft-rcon`** skill to reload in-game without restarting `mc-forge-server`:
  - Paradigm Essentials configs: `paradigm reload`
- **Startup-only configs (`user_jvm_args.txt`, `docker-compose.yml`, non-reloadable `.toml` configs):**
  1. Activate **`minecraft-rcon`** to check `list` and run `save-all`.
  2. Obtain explicit user confirmation before restarting `mc-forge-server`.
  3. Run `make restart` (or `docker compose up -d` if `docker-compose.yml` changed) and inspect `make logs` to confirm healthy startup.

---

### Step 4: Synchronize with `server-config/` (Final Step)
After verifying configuration edits in `data/`, activate the **`minecraft-config-sync`** skill (`pull_configs.py` / `diff_configs.py` or `make config-pull`) to persist safe, secret-free changes into the Git-tracked `server-config/` directory.
