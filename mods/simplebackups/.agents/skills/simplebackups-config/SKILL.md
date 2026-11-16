---
name: simplebackups-config
description: >-
  Manage and synchronize simplebackups server configurations between mods/simplebackups/configs/ and data/.
---

# simplebackups Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `simplebackups` between `mods/simplebackups/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/simplebackups/configs/simplebackups-common.toml` $\leftrightarrow$ `data/config/simplebackups-common.toml`
- `mods/simplebackups/configs/simplebackups-server.toml` $\leftrightarrow$ `data/world/serverconfig/simplebackups-server.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/simplebackups/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/simplebackups/.agents/skills/simplebackups-config/scripts/sync_config.py push --dry-run
   python3 mods/simplebackups/.agents/skills/simplebackups-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/simplebackups/.agents/skills/simplebackups-config/scripts/sync_config.py diff
   python3 mods/simplebackups/.agents/skills/simplebackups-config/scripts/sync_config.py pull --dry-run
   python3 mods/simplebackups/.agents/skills/simplebackups-config/scripts/sync_config.py pull
   ```
