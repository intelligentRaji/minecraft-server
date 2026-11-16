---
name: farmersdelight-config
description: >-
  Manage and synchronize farmersdelight server configurations between mods/farmersdelight/configs/ and data/.
---

# farmersdelight Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `farmersdelight` between `mods/farmersdelight/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/farmersdelight/configs/farmersdelight-common.toml` $\leftrightarrow$ `data/config/farmersdelight-common.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/farmersdelight/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/farmersdelight/.agents/skills/farmersdelight-config/scripts/sync_config.py push --dry-run
   python3 mods/farmersdelight/.agents/skills/farmersdelight-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/farmersdelight/.agents/skills/farmersdelight-config/scripts/sync_config.py diff
   python3 mods/farmersdelight/.agents/skills/farmersdelight-config/scripts/sync_config.py pull --dry-run
   python3 mods/farmersdelight/.agents/skills/farmersdelight-config/scripts/sync_config.py pull
   ```
