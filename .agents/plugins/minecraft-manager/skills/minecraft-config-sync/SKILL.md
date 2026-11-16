---
name: minecraft-config-sync
description: >-
  Synchronize, diff, and prune versioned Minecraft Forge 1.20.1 server
  configurations between runtime data/ and Git-tracked server-config/ with
  secret and privacy scanning.
---

# Minecraft Configuration Synchronization Runbook

Procedures for keeping the Git-tracked `server-config/` directory synchronized with live runtime configurations in `data/` without exposing secrets or player state.

---

### Step 1: Preview & Pull Live Configs into `server-config/`
Always preview with `--dry-run` before writing:

```bash
# Preview pull from data/ to server-config/:
python3 .agents/plugins/minecraft-manager/skills/minecraft-config-sync/scripts/pull_configs.py --dry-run

# Pull allowlisted configs into server-config/:
python3 .agents/plugins/minecraft-manager/skills/minecraft-config-sync/scripts/pull_configs.py

# Pull and prune files removed or newly excluded from data/:
python3 .agents/plugins/minecraft-manager/skills/minecraft-config-sync/scripts/pull_configs.py --prune
```
*(Or use `make config-pull-dry` / `make config-pull`.)*

---

### Step 2: Diff Tracked vs. Runtime Configs
Inspect configuration drift between `server-config/` and `data/`:

```bash
# Print unified diff:
python3 .agents/plugins/minecraft-manager/skills/minecraft-config-sync/scripts/diff_configs.py

# Exit with code 1 if differences exist (for CI/scripted checks):
python3 .agents/plugins/minecraft-manager/skills/minecraft-config-sync/scripts/diff_configs.py --exit-code
```
*(Or use `make config-diff`.)*

---

### Step 3: Push Versioned Configs to Runtime `data/`
Apply tracked configuration files from `server-config/` onto `data/` while preserving target file ownership and permissions:

```bash
# Preview push without modifying data/:
python3 .agents/plugins/minecraft-manager/skills/minecraft-config-sync/scripts/push_configs.py --dry-run

# Apply server-config/ changes into data/:
python3 .agents/plugins/minecraft-manager/skills/minecraft-config-sync/scripts/push_configs.py
```
*(Or use `make config-push-dry` / `make config-push`.)*

---

### Tracked vs. Excluded Invariants
- **Tracked in `server-config/`:**
  - `user_jvm_args.txt`
  - `config/**` and `defaultconfigs/**` (`.json`, `.toml`, `.cfg`, `.conf`, `.properties`, `.yml`, `.yaml`, `.txt`)
  - `world/serverconfig/*.toml`
  - `config/luckperms/luckperms-snapshot.json` *(managed via **`minecraft-permission-manager`**; preserved by `--prune` and skipped by `push`/`diff`)*
- **Excluded (never pulled or committed):**
  - Secrets and credentials (`config/paradigm/discord.json`, `config/paradigm/storage.json`, `config/luckperms/luckperms.conf`), plus any line matching secret keys, webhook URLs, URI credentials, PEM private keys, or JWTs
  - Databases, logs, archives, and binaries (`*.db`, `*.mv.db`, `*.trace.db`, `*.sqlite*`, `*.jar`, `*.log`, `*.gz`, `*.zip`, `*.tar*`)
  - Runtime/cache directories (`libs/`, `data/`, `cache/`, `translations/`, `tmp/`)
  - `corecommands` player runtime state (`afkstatus.json`, `deathlocation.json`, `homes.json`, `lastlocation.json`, `lastmessagerecipient.json`, `logoutposition.json`, `playerjoinstatus.json`, `tparequests.json`)
  - `server.properties` and `world/` region/playerdata files
