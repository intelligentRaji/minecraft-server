---
name: modernfix-config
description: >-
  Manage and synchronize modernfix server configurations between mods/modernfix/configs/ and data/.
---

# modernfix Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `modernfix` between `mods/modernfix/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/modernfix/configs/ferritecore-mixin.toml` $\leftrightarrow$ `data/config/ferritecore-mixin.toml`
- `mods/modernfix/configs/modernfix-common.toml` $\leftrightarrow$ `data/config/modernfix-common.toml`
- `mods/modernfix/configs/modernfix-mixins.properties` $\leftrightarrow$ `data/config/modernfix-mixins.properties`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/modernfix/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/modernfix/.agents/skills/modernfix-config/scripts/sync_config.py push --dry-run
   python3 mods/modernfix/.agents/skills/modernfix-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/modernfix/.agents/skills/modernfix-config/scripts/sync_config.py diff
   python3 mods/modernfix/.agents/skills/modernfix-config/scripts/sync_config.py pull --dry-run
   python3 mods/modernfix/.agents/skills/modernfix-config/scripts/sync_config.py pull
   ```
