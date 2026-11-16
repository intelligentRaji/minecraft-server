---
name: distant-horizons-config
description: >-
  Manage and synchronize distant-horizons server configurations between mods/distant-horizons/configs/ and data/.
---

# distant-horizons Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `distant-horizons` between `mods/distant-horizons/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/distant-horizons/configs/DistantHorizons.toml` $\leftrightarrow$ `data/config/DistantHorizons.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/distant-horizons/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/distant-horizons/.agents/skills/distant-horizons-config/scripts/sync_config.py push --dry-run
   python3 mods/distant-horizons/.agents/skills/distant-horizons-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/distant-horizons/.agents/skills/distant-horizons-config/scripts/sync_config.py diff
   python3 mods/distant-horizons/.agents/skills/distant-horizons-config/scripts/sync_config.py pull --dry-run
   python3 mods/distant-horizons/.agents/skills/distant-horizons-config/scripts/sync_config.py pull
   ```
