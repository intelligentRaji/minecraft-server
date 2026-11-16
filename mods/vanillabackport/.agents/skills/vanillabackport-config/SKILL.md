---
name: vanillabackport-config
description: >-
  Manage and synchronize vanillabackport server configurations between mods/vanillabackport/configs/ and data/.
---

# vanillabackport Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `vanillabackport` between `mods/vanillabackport/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/vanillabackport/configs/vanillabackport-common.toml` $\leftrightarrow$ `data/config/vanillabackport-common.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/vanillabackport/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/vanillabackport/.agents/skills/vanillabackport-config/scripts/sync_config.py push --dry-run
   python3 mods/vanillabackport/.agents/skills/vanillabackport-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/vanillabackport/.agents/skills/vanillabackport-config/scripts/sync_config.py diff
   python3 mods/vanillabackport/.agents/skills/vanillabackport-config/scripts/sync_config.py pull --dry-run
   python3 mods/vanillabackport/.agents/skills/vanillabackport-config/scripts/sync_config.py pull
   ```
