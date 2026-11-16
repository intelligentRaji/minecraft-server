# SimpleBackups — Configuration Rules (`mods/simplebackups/`)

## 1. Configuration Scope (`mods/simplebackups/configs/`)
- Edit SimpleBackups configuration files directly inside `mods/simplebackups/configs/` (`simplebackups-common.toml` and `simplebackups-server.toml`).
- For section details, schema conventions, and invariants, activate the [`simplebackups-config` skill](file:///home/wakaria/dev/minecraft-server/mods/simplebackups/.agents/skills/simplebackups-config/SKILL.md).

## 2. Server Invariants
1. **Relative Output Path (`simplebackups-common.toml`):**
   - `outputPath` **must** remain `"simplebackups"` (relative path inside the server data directory).
2. **Command Permission Guard (`simplebackups-server.toml`):**
   - `commandsCheatsDisabled` **must** remain `false` on multiplayer servers so unprivileged players cannot trigger backup commands.
3. **Valid Ranges & Enums (`simplebackups-common.toml`):**
   - `backupType`: `FULL_BACKUPS`, `MODIFIED_SINCE_LAST`, or `MODIFIED_SINCE_FULL`.
   - `timer`: `1` to `32767` (minutes).
   - `backupsToKeep`: `1` to `32767`.
   - `fullBackupTimer`: `1` to `5259600` (minutes).
   - `compressionLevel`: `-1` to `9` (`-1` default, `0` none, `9` maximum).
   - `maxDiskSize`: `<number> <B|KB|MB|GB|TB>` (e.g., `"25 GB"`).

## 3. Sanitized & Excluded Files
- Never add backup archives (`*.zip`, `*.tar`, `*.gz`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`, `*.db`, `*.jar`) or `simplebackups/`, `logs/`, or `world/` directories to `mods/simplebackups/configs/`.
