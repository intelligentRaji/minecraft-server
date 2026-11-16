---
name: minecraft-config-manager
description: >-
  Route Minecraft Forge 1.20.1 server, mod, and world configuration tasks to the
  target mod's vertical slice (mods/<slug>/) and <slug>-config skill while
  enforcing zero-downtime reload rules and secret/invariant guards.
---

# Minecraft Configuration Management Runbook

High-level router for inspecting, editing, validating, and applying Minecraft Forge 1.20.1 server, mod, and world configurations across per-mod vertical slices (`mods/<slug>/`).

---

### Step 1: Locate Target Configuration Scope
- **Core server properties (`server.properties` keys):** Edit environment variables in [docker-compose.yml](file:///home/wakaria/dev/minecraft-server/docker-compose.yml) or `.env` (`itzg/minecraft-server` regenerates `data/server.properties` on startup—never edit or commit `data/server.properties`).
- **Installed mods & core Forge/JVM settings:** Each configured mod owns a self-contained vertical slice under `mods/<slug>/`:
  - `mods/<slug>/configs/` — Git-tracked config files
  - `mods/<slug>/.agents/skills/<slug>-config/SKILL.md` — Per-mod skill runbook
  - `mods/<slug>/.agents/skills/<slug>-config/scripts/sync_config.py` — Mod-specific `push`, `pull`, `diff`, and `mappings` script
- **Unmapped or newly generated mod configs:** Activate **`minecraft-mod-harness-manager`** (`audit_unmapped.py` / `make config-unmapped`) to inspect unclaimed config files in `data/` and scaffold a new `mods/<slug>/` slice.

---

### Step 2: Delegate Mod Edits to `<slug>-config`
1. Activate the target mod's **`<slug>-config`** skill (for example `paradigm-config`, `create-config`, `biomesoplenty-config`, or `server-core-config`).
2. Edit files in `mods/<slug>/configs/`, then run that mod's `sync_config.py push` (previewing with `--dry-run` first) to copy changes into `data/`.
3. If an in-game command modified a config dynamically in `data/`, run that mod's `sync_config.py pull` to save safe changes back into `mods/<slug>/configs/`.

---

### Step 3: Enforce Configuration Invariants
Per [minecraft-server-operations.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/rules/minecraft-server-operations.md):
- `mods/paradigm/configs/main.json` must keep `"internalPermissionsEnable.value"` set to `false`.
- `mods/server-core/configs/forge-server.toml` must keep `permissionHandler = "luckperms:permission_handler"`.
- `mods/paradigm/configs/chat.json` and `tablist.json` must preserve `{prefix}{player_name}{suffix}` formatting.

---

### Step 4: Apply Changes Live or Restart When Required
- **Live-reloadable configs (Zero-Downtime First):**
  Activate the **`minecraft-rcon`** skill to reload without restarting `mc-forge-server`:
  - Paradigm Essentials configs: `paradigm reload`
- **Startup-only configs (`user_jvm_args.txt`, `docker-compose.yml`, non-reloadable `.toml` configs):**
  1. Activate **`minecraft-rcon`** to check `list` and run `save-all`.
  2. Obtain explicit user confirmation before restarting `mc-forge-server`.
  3. Run `make restart` (or `make up` when `docker-compose.yml` changed; `make up` automatically runs `config-push` before `docker compose up -d`).
