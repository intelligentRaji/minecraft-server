---
name: biomesoplenty-config
description: >-
  Manage and synchronize biomesoplenty server configurations between mods/biomesoplenty/configs/ and data/.
---

# biomesoplenty Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `biomesoplenty` between `mods/biomesoplenty/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/biomesoplenty/configs/biome_toggles.json` $\leftrightarrow$ `data/config/biomesoplenty/biome_toggles.json`
- `mods/biomesoplenty/configs/gameplay.toml` $\leftrightarrow$ `data/config/biomesoplenty/gameplay.toml`
- `mods/biomesoplenty/configs/generation.toml` $\leftrightarrow$ `data/config/biomesoplenty/generation.toml`

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/biomesoplenty/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/biomesoplenty/.agents/skills/biomesoplenty-config/scripts/sync_config.py push --dry-run
   python3 mods/biomesoplenty/.agents/skills/biomesoplenty-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/biomesoplenty/.agents/skills/biomesoplenty-config/scripts/sync_config.py diff
   python3 mods/biomesoplenty/.agents/skills/biomesoplenty-config/scripts/sync_config.py pull --dry-run
   python3 mods/biomesoplenty/.agents/skills/biomesoplenty-config/scripts/sync_config.py pull
   ```
