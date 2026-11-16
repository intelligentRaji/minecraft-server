---
name: sliceanddice-config
description: >-
  Manage and synchronize sliceanddice server configurations between mods/sliceanddice/configs/ and data/.
---

# sliceanddice Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `sliceanddice` between `mods/sliceanddice/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/sliceanddice/configs/sliceanddice-common.toml` $\leftrightarrow$ `data/config/sliceanddice-common.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/sliceanddice/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/sliceanddice/.agents/skills/sliceanddice-config/scripts/sync_config.py push --dry-run
   python3 mods/sliceanddice/.agents/skills/sliceanddice-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/sliceanddice/.agents/skills/sliceanddice-config/scripts/sync_config.py diff
   python3 mods/sliceanddice/.agents/skills/sliceanddice-config/scripts/sync_config.py pull --dry-run
   python3 mods/sliceanddice/.agents/skills/sliceanddice-config/scripts/sync_config.py pull
   ```
