---
name: jei-config
description: Inspect and configure Just Enough Items (JEI) server-side cheat-mode permissions (operator, creative mode, and /give permissions) in mods/jei/configs/.
---

# Just Enough Items Configuration Guide (`jei-config`)

Use this skill to inspect and configure **Just Enough Items** (`jei`) server-side cheat permissions in `mods/jei/configs/`.

> **Startup-Only Configuration:** JEI server-side settings are read during dedicated server initialization and world load; they are not hot-reloadable. Edits made in `mods/jei/configs/` require an `mc-forge-server` restart to take effect. Always obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online before restarting.

---

## 1. Configuration File Overview (`mods/jei/configs/`)

JEI server configuration uses mezz's custom INI format (`mezz_config`). Two file paths are maintained in `mods/jei/configs/`:

| File | Purpose | Format |
| :--- | :--- | :--- |
| `config/jei/server/world/default/jei-server.ini` | Server-wide default template applied when creating or initializing new worlds. | INI (`mezz_config`) |
| `world/serverconfig/jei/jei-server.ini` | Active per-world server configuration applied to the running world. | INI (`mezz_config`) |

Both files must retain identical settings to avoid drift between newly generated worlds/dimensions and the active game world.

---

## 2. Configuration Schema & Format

JEI server INI files define a single `[permissions]` section with inline comment annotations:

```ini
# Name: Server Cheat Permissions
# Description: Choose who can use JEI cheat mode on this server.
[permissions]
	# Name: Allow Cheat Mode for Operators
	# Description: Allow players with operator status (/op) to use JEI cheat mode.
	# Valid Values: [true, false]
	# Default Value: true
	enableCheatModeForOp = true

	# Name: Allow Cheat Mode in Creative Mode
	# Description: Allow players in Creative Mode to use JEI cheat mode.
	# Valid Values: [true, false]
	# Default Value: true
	enableCheatModeForCreative = true

	# Name: Allow Cheat Mode with Give Permission
	# Description: Allow players who can use the /give command to use JEI cheat mode.
	# Valid Values: [true, false]
	# Default Value: false
	enableCheatModeForGive = false
```

### Key Reference (`[permissions]`)

| Key | Type | Default | Valid Values | Description |
| :--- | :--- | :--- | :--- | :--- |
| `enableCheatModeForOp` | `bool` | `true` | `true`, `false` | When `true`, players with server operator status (`/op`, permission level 2+) can click items in the JEI item list to cheat them directly into their inventory. |
| `enableCheatModeForCreative` | `bool` | `true` | `true`, `false` | When `true`, players currently in Creative Mode (`gamemode creative`) are permitted to cheat items via JEI without requiring server operator status. |
| `enableCheatModeForGive` | `bool` | `false` | `true`, `false` | When `true`, any player who has permission to execute the `/give` command (e.g. through LuckPerms permission `minecraft.command.give`) can use JEI cheat mode. |

---

## 3. Mandatory Server Invariants

1. **Exact Keys & Section:**
   - The file must contain only the `[permissions]` section header.
   - Only the three documented keys (`enableCheatModeForOp`, `enableCheatModeForCreative`, `enableCheatModeForGive`) are allowed.
   - Values must be lowercase booleans: `true` or `false`.
2. **Dual-File Synchronization:**
   - Always update both `config/jei/server/world/default/jei-server.ini` and `world/serverconfig/jei/jei-server.ini` in tandem with identical values.
3. **Excluded & Client-Only Files:**
   - Do NOT add client-side JEI configs (`jei-client.ini`, `jei-mod-id-format.ini`, sort-order `.ini` files, or `blacklist.cfg`) to `mods/jei/configs/`.
   - Never place runtime state directories (`logs/`, `mods/`, `playerdata/`, `region/`, `entities/`, `poi/`), world backups (`world_backup_*`), symlinks, secrets, or binary/archive artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/jei/configs/`.
