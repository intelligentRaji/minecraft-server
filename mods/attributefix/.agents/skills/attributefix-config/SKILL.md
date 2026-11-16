---
name: attributefix-config
description: >-
  Manage and synchronize attributefix server configurations between mods/attributefix/configs/ and data/.
---

# attributefix Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `attributefix` between `mods/attributefix/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/attributefix/configs/attributefix.json` $\leftrightarrow$ `data/config/attributefix.json`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/attributefix/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/attributefix/.agents/skills/attributefix-config/scripts/sync_config.py push --dry-run
   python3 mods/attributefix/.agents/skills/attributefix-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/attributefix/.agents/skills/attributefix-config/scripts/sync_config.py diff
   python3 mods/attributefix/.agents/skills/attributefix-config/scripts/sync_config.py pull --dry-run
   python3 mods/attributefix/.agents/skills/attributefix-config/scripts/sync_config.py pull
   ```
