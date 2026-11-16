---
name: botania-config
description: >-
  Manage and synchronize botania server configurations between mods/botania/configs/ and data/.
---

# botania Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `botania` between `mods/botania/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/botania/configs/botania-common.toml` $\leftrightarrow$ `data/config/botania-common.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/botania/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/botania/.agents/skills/botania-config/scripts/sync_config.py push --dry-run
   python3 mods/botania/.agents/skills/botania-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/botania/.agents/skills/botania-config/scripts/sync_config.py diff
   python3 mods/botania/.agents/skills/botania-config/scripts/sync_config.py pull --dry-run
   python3 mods/botania/.agents/skills/botania-config/scripts/sync_config.py pull
   ```
