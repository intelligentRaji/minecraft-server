---
name: jade-config
description: >-
  Manage and synchronize jade server configurations between mods/jade/configs/ and data/.
---

# jade Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `jade` between `mods/jade/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/jade/configs/server-plugin-overrides.json` $\leftrightarrow$ `data/config/jade/server-plugin-overrides.json`
- `mods/jade/configs/sort-order.json` $\leftrightarrow$ `data/config/jade/sort-order.json`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/jade/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/jade/.agents/skills/jade-config/scripts/sync_config.py push --dry-run
   python3 mods/jade/.agents/skills/jade-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/jade/.agents/skills/jade-config/scripts/sync_config.py diff
   python3 mods/jade/.agents/skills/jade-config/scripts/sync_config.py pull --dry-run
   python3 mods/jade/.agents/skills/jade-config/scripts/sync_config.py pull
   ```
