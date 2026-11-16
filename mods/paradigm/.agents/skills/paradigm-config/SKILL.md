---
name: paradigm-config
description: >-
  Manage and synchronize paradigm server configurations between mods/paradigm/configs/ and data/.
---

# paradigm Configuration Runbook

Manage, validate, and synchronize tracked configuration files for `paradigm` between `mods/paradigm/configs/` and runtime `data/`.

### Tracked File Mappings
- `mods/paradigm/configs/afk.json` $\leftrightarrow$ `data/config/paradigm/afk.json`
- `mods/paradigm/configs/announcements.json` $\leftrightarrow$ `data/config/paradigm/announcements.json`
- `mods/paradigm/configs/chat.json` $\leftrightarrow$ `data/config/paradigm/chat.json`
- `mods/paradigm/configs/commands.json` $\leftrightarrow$ `data/config/paradigm/commands.json`
- `mods/paradigm/configs/commands/examples.json` $\leftrightarrow$ `data/config/paradigm/commands/examples.json`
- `mods/paradigm/configs/dashboard.json` $\leftrightarrow$ `data/config/paradigm/dashboard.json`
- `mods/paradigm/configs/emojis.json` $\leftrightarrow$ `data/config/paradigm/emojis.json`
- `mods/paradigm/configs/holograms.json` $\leftrightarrow$ `data/config/paradigm/holograms.json`
- `mods/paradigm/configs/lang/cs.json` $\leftrightarrow$ `data/config/paradigm/lang/cs.json`
- `mods/paradigm/configs/lang/en.json` $\leftrightarrow$ `data/config/paradigm/lang/en.json`
- `mods/paradigm/configs/lang/ru.json` $\leftrightarrow$ `data/config/paradigm/lang/ru.json`
- `mods/paradigm/configs/main.json` $\leftrightarrow$ `data/config/paradigm/main.json`
- `mods/paradigm/configs/mentions.json` $\leftrightarrow$ `data/config/paradigm/mentions.json`
- `mods/paradigm/configs/moderation-settings.json` $\leftrightarrow$ `data/config/paradigm/moderation-settings.json`
- `mods/paradigm/configs/motd.json` $\leftrightarrow$ `data/config/paradigm/motd.json`
- `mods/paradigm/configs/restarts.json` $\leftrightarrow$ `data/config/paradigm/restarts.json`
- `mods/paradigm/configs/tablist.json` $\leftrightarrow$ `data/config/paradigm/tablist.json`
- `mods/paradigm/configs/tickets.json` $\leftrightarrow$ `data/config/paradigm/tickets.json`

### Excluded Runtime / Sensitive Paths
- `data/config/paradigm/cooldowns.json` *(never synced or committed)*
- `data/config/paradigm/discord.json` *(never synced or committed)*
- `data/config/paradigm/discovered_permissions.json` *(never synced or committed)*
- `data/config/paradigm/storage.json` *(never synced or committed)*

### Invariants
- `main.json` must keep `"internalPermissionsEnable.value": false`.

---

### Workflow

1. **Edit Configs:** Modify files inside `mods/paradigm/configs/`.
2. **Preview & Push to `data/`:**
   ```bash
   python3 mods/paradigm/.agents/skills/paradigm-config/scripts/sync_config.py push --dry-run
   python3 mods/paradigm/.agents/skills/paradigm-config/scripts/sync_config.py push
   ```
3. **Inspect Drift or Pull Runtime Edits:**
   ```bash
   python3 mods/paradigm/.agents/skills/paradigm-config/scripts/sync_config.py diff
   python3 mods/paradigm/.agents/skills/paradigm-config/scripts/sync_config.py pull --dry-run
   python3 mods/paradigm/.agents/skills/paradigm-config/scripts/sync_config.py pull
   ```
