---
name: twilightforest-config
description: >-
  Manage and synchronize twilightforest server configurations between mods/twilightforest/configs/ and data/.
---

# twilightforest Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `twilightforest` between `mods/twilightforest/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/twilightforest/configs/twilightforest-common.toml` $\leftrightarrow$ `data/config/twilightforest-common.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/twilightforest/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/twilightforest/.agents/skills/twilightforest-config/scripts/sync_config.py push --dry-run
   python3 mods/twilightforest/.agents/skills/twilightforest-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/twilightforest/.agents/skills/twilightforest-config/scripts/sync_config.py diff
   python3 mods/twilightforest/.agents/skills/twilightforest-config/scripts/sync_config.py pull --dry-run
   python3 mods/twilightforest/.agents/skills/twilightforest-config/scripts/sync_config.py pull
   ```
