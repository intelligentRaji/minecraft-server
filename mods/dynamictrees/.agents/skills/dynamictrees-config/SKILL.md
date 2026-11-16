---
name: dynamictrees-config
description: >-
  Manage and synchronize dynamictrees server configurations between mods/dynamictrees/configs/ and data/.
---

# dynamictrees Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `dynamictrees` between `mods/dynamictrees/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/dynamictrees/configs/dynamictrees-common.toml` $\leftrightarrow$ `data/config/dynamictrees-common.toml`
- `mods/dynamictrees/configs/dynamictrees-server.toml` $\leftrightarrow$ `data/world/serverconfig/dynamictrees-server.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/dynamictrees/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/dynamictrees/.agents/skills/dynamictrees-config/scripts/sync_config.py push --dry-run
   python3 mods/dynamictrees/.agents/skills/dynamictrees-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/dynamictrees/.agents/skills/dynamictrees-config/scripts/sync_config.py diff
   python3 mods/dynamictrees/.agents/skills/dynamictrees-config/scripts/sync_config.py pull --dry-run
   python3 mods/dynamictrees/.agents/skills/dynamictrees-config/scripts/sync_config.py pull
   ```
