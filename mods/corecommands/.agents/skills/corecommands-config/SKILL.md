---
name: corecommands-config
description: >-
  Manage and synchronize corecommands server configurations between mods/corecommands/configs/ and data/.
---

# corecommands Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `corecommands` between `mods/corecommands/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/corecommands/configs/config.json` $\leftrightarrow$ `data/config/corecommands/config.json`
- `mods/corecommands/configs/rules.json` $\leftrightarrow$ `data/config/corecommands/rules.json`
- `mods/corecommands/configs/spawn.json` $\leftrightarrow$ `data/config/corecommands/spawn.json`
- `mods/corecommands/configs/warps.json` $\leftrightarrow$ `data/config/corecommands/warps.json`

### Excluded Runtime / Sensitive Paths
- `data/config/corecommands/afkstatus.json` *(never synced or committed)*
- `data/config/corecommands/deathlocation.json` *(never synced or committed)*
- `data/config/corecommands/homes.json` *(never synced or committed)*
- `data/config/corecommands/lastlocation.json` *(never synced or committed)*
- `data/config/corecommands/lastmessagerecipient.json` *(never synced or committed)*
- `data/config/corecommands/logoutposition.json` *(never synced or committed)*
- `data/config/corecommands/playerjoinstatus.json` *(never synced or committed)*
- `data/config/corecommands/tparequests.json` *(never synced or committed)*

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/corecommands/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/corecommands/.agents/skills/corecommands-config/scripts/sync_config.py push --dry-run
   python3 mods/corecommands/.agents/skills/corecommands-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/corecommands/.agents/skills/corecommands-config/scripts/sync_config.py diff
   python3 mods/corecommands/.agents/skills/corecommands-config/scripts/sync_config.py pull --dry-run
   python3 mods/corecommands/.agents/skills/corecommands-config/scripts/sync_config.py pull
   ```
