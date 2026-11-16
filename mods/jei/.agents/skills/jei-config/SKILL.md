---
name: jei-config
description: >-
  Manage and synchronize jei server configurations between mods/jei/configs/ and data/.
---

# jei Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `jei` between `mods/jei/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/jei/configs/jei/server/world/default/jei-server.ini` $\leftrightarrow$ `data/config/jei/server/world/default/jei-server.ini`
- `mods/jei/configs/jeresources-common.toml` $\leftrightarrow$ `data/config/jeresources-common.toml`
- `mods/jei/configs/jeresources.toml` $\leftrightarrow$ `data/config/jeresources.toml`
- `mods/jei/configs/world-jei/jei-server.ini` $\leftrightarrow$ `data/world/serverconfig/jei/jei-server.ini`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/jei/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/jei/.agents/skills/jei-config/scripts/sync_config.py push --dry-run
   python3 mods/jei/.agents/skills/jei-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/jei/.agents/skills/jei-config/scripts/sync_config.py diff
   python3 mods/jei/.agents/skills/jei-config/scripts/sync_config.py pull --dry-run
   python3 mods/jei/.agents/skills/jei-config/scripts/sync_config.py pull
   ```
