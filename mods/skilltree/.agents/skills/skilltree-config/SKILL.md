---
name: skilltree-config
description: >-
  Manage and synchronize skilltree server configurations between mods/skilltree/configs/ and data/.
---

# skilltree Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `skilltree` between `mods/skilltree/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/skilltree/configs/skilltree-common.toml` $\leftrightarrow$ `data/config/skilltree-common.toml`
- `mods/skilltree/configs/skilltree-server.toml` $\leftrightarrow$ `data/world/serverconfig/skilltree-server.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/skilltree/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/skilltree/.agents/skills/skilltree-config/scripts/sync_config.py push --dry-run
   python3 mods/skilltree/.agents/skills/skilltree-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/skilltree/.agents/skills/skilltree-config/scripts/sync_config.py diff
   python3 mods/skilltree/.agents/skills/skilltree-config/scripts/sync_config.py pull --dry-run
   python3 mods/skilltree/.agents/skills/skilltree-config/scripts/sync_config.py pull
   ```
