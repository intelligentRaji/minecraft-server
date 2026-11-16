---
name: spark-config
description: >-
  Manage and synchronize spark server configurations between mods/spark/configs/ and data/.
---

# spark Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `spark` between `mods/spark/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/spark/configs/config.json` $\leftrightarrow$ `data/config/spark/config.json`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/spark/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/spark/.agents/skills/spark-config/scripts/sync_config.py push --dry-run
   python3 mods/spark/.agents/skills/spark-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/spark/.agents/skills/spark-config/scripts/sync_config.py diff
   python3 mods/spark/.agents/skills/spark-config/scripts/sync_config.py pull --dry-run
   python3 mods/spark/.agents/skills/spark-config/scripts/sync_config.py pull
   ```
