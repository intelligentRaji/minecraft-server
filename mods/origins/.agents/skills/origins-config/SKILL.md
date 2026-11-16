---
name: origins-config
description: >-
  Manage and synchronize origins server configurations between mods/origins/configs/ and data/.
---

# origins Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `origins` between `mods/origins/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/origins/configs/apoli-common.toml` $\leftrightarrow$ `data/config/apoli-common.toml`
- `mods/origins/configs/apoli-server.toml` $\leftrightarrow$ `data/world/serverconfig/apoli-server.toml`
- `mods/origins/configs/calio-common.toml` $\leftrightarrow$ `data/config/calio-common.toml`
- `mods/origins/configs/origins-common.toml` $\leftrightarrow$ `data/config/origins-common.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/origins/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/origins/.agents/skills/origins-config/scripts/sync_config.py push --dry-run
   python3 mods/origins/.agents/skills/origins-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/origins/.agents/skills/origins-config/scripts/sync_config.py diff
   python3 mods/origins/.agents/skills/origins-config/scripts/sync_config.py pull --dry-run
   python3 mods/origins/.agents/skills/origins-config/scripts/sync_config.py pull
   ```
