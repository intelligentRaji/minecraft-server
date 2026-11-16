---
name: create-config
description: >-
  Manage and synchronize create server configurations between mods/create/configs/ and data/.
---

# create Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `create` between `mods/create/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/create/configs/create-common.toml` $\leftrightarrow$ `data/config/create-common.toml`
- `mods/create/configs/create-server.toml` $\leftrightarrow$ `data/world/serverconfig/create-server.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/create/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/create/.agents/skills/create-config/scripts/sync_config.py push --dry-run
   python3 mods/create/.agents/skills/create-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/create/.agents/skills/create-config/scripts/sync_config.py diff
   python3 mods/create/.agents/skills/create-config/scripts/sync_config.py pull --dry-run
   python3 mods/create/.agents/skills/create-config/scripts/sync_config.py pull
   ```
