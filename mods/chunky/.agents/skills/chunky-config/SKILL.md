---
name: chunky-config
description: >-
  Manage and synchronize chunky server configurations between mods/chunky/configs/ and data/.
---

# chunky Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `chunky` between `mods/chunky/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/chunky/configs/config.json` $\leftrightarrow$ `data/config/chunky/config.json`

### Excluded Runtime / Sensitive Paths
- `data/config/chunky/tasks/minecraft/overworld.properties` *(never synced or committed)*

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/chunky/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/chunky/.agents/skills/chunky-config/scripts/sync_config.py push --dry-run
   python3 mods/chunky/.agents/skills/chunky-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/chunky/.agents/skills/chunky-config/scripts/sync_config.py diff
   python3 mods/chunky/.agents/skills/chunky-config/scripts/sync_config.py pull --dry-run
   python3 mods/chunky/.agents/skills/chunky-config/scripts/sync_config.py pull
   ```
