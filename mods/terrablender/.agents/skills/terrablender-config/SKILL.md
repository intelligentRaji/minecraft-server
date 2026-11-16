---
name: terrablender-config
description: >-
  Manage and synchronize terrablender server configurations between mods/terrablender/configs/ and data/.
---

# terrablender Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `terrablender` between `mods/terrablender/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/terrablender/configs/terrablender.toml` $\leftrightarrow$ `data/config/terrablender.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/terrablender/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/terrablender/.agents/skills/terrablender-config/scripts/sync_config.py push --dry-run
   python3 mods/terrablender/.agents/skills/terrablender-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/terrablender/.agents/skills/terrablender-config/scripts/sync_config.py diff
   python3 mods/terrablender/.agents/skills/terrablender-config/scripts/sync_config.py pull --dry-run
   python3 mods/terrablender/.agents/skills/terrablender-config/scripts/sync_config.py pull
   ```
