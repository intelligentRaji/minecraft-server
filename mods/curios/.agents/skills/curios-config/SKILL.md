---
name: curios-config
description: >-
  Manage and synchronize curios server configurations between mods/curios/configs/ and data/.
---

# curios Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `curios` between `mods/curios/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/curios/configs/curios-common.toml` $\leftrightarrow$ `data/config/curios-common.toml`
- `mods/curios/configs/curios-server.toml` $\leftrightarrow$ `data/world/serverconfig/curios-server.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/curios/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/curios/.agents/skills/curios-config/scripts/sync_config.py push --dry-run
   python3 mods/curios/.agents/skills/curios-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/curios/.agents/skills/curios-config/scripts/sync_config.py diff
   python3 mods/curios/.agents/skills/curios-config/scripts/sync_config.py pull --dry-run
   python3 mods/curios/.agents/skills/curios-config/scripts/sync_config.py pull
   ```
