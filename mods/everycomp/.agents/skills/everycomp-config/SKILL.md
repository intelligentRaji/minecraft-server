---
name: everycomp-config
description: >-
  Manage and synchronize everycomp server configurations between mods/everycomp/configs/ and data/.
---

# everycomp Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `everycomp` between `mods/everycomp/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/everycomp/configs/everycomp-common.toml` $\leftrightarrow$ `data/config/everycomp-common.toml`
- `mods/everycomp/configs/everycomp-entries.toml` $\leftrightarrow$ `data/config/everycomp-entries.toml`
- `mods/everycomp/configs/everycomp-hazardous.toml` $\leftrightarrow$ `data/config/everycomp-hazardous.toml`
- `mods/everycomp/configs/moonlight-common.toml` $\leftrightarrow$ `data/config/moonlight-common.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/everycomp/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/everycomp/.agents/skills/everycomp-config/scripts/sync_config.py push --dry-run
   python3 mods/everycomp/.agents/skills/everycomp-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/everycomp/.agents/skills/everycomp-config/scripts/sync_config.py diff
   python3 mods/everycomp/.agents/skills/everycomp-config/scripts/sync_config.py pull --dry-run
   python3 mods/everycomp/.agents/skills/everycomp-config/scripts/sync_config.py pull
   ```
