---
name: luckperms-config
description: >-
  Manage and synchronize luckperms server configurations between mods/luckperms/configs/ and data/.
---

# luckperms Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `luckperms` between `mods/luckperms/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/luckperms/configs/contexts.json` $\leftrightarrow$ `data/config/luckperms/contexts.json`

### Excluded Runtime / Sensitive Paths
- `data/config/luckperms/luckperms.conf` *(never synced or committed)*

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/luckperms/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/luckperms/.agents/skills/luckperms-config/scripts/sync_config.py push --dry-run
   python3 mods/luckperms/.agents/skills/luckperms-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/luckperms/.agents/skills/luckperms-config/scripts/sync_config.py diff
   python3 mods/luckperms/.agents/skills/luckperms-config/scripts/sync_config.py pull --dry-run
   python3 mods/luckperms/.agents/skills/luckperms-config/scripts/sync_config.py pull
   ```
