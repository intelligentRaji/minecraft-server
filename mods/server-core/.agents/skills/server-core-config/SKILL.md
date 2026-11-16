---
name: server-core-config
description: >-
  Manage and synchronize server-core server configurations between mods/server-core/configs/ and data/.
---

# server-core Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `server-core` between `mods/server-core/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/server-core/configs/fml.toml` $\leftrightarrow$ `data/config/fml.toml`
- `mods/server-core/configs/forge-server.toml` $\leftrightarrow$ `data/world/serverconfig/forge-server.toml`
- `mods/server-core/configs/user_jvm_args.txt` $\leftrightarrow$ `data/user_jvm_args.txt`

### Invariants
- `forge-server.toml` must keep `permissionHandler = "luckperms:permission_handler"`.

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/server-core/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/server-core/.agents/skills/server-core-config/scripts/sync_config.py push --dry-run
   python3 mods/server-core/.agents/skills/server-core-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/server-core/.agents/skills/server-core-config/scripts/sync_config.py diff
   python3 mods/server-core/.agents/skills/server-core-config/scripts/sync_config.py pull --dry-run
   python3 mods/server-core/.agents/skills/server-core-config/scripts/sync_config.py pull
   ```
