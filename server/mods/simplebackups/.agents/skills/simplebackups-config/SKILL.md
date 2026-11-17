---
name: simplebackups-config
description: Inspect and configure SimpleBackups settings (backup schedule, retention, compression, error handling, ignore rules, mod compatibility, and command permissions) in mods/simplebackups/configs/.
---

# SimpleBackups Configuration Guide (`simplebackups-config`)

Use this skill to inspect and modify **SimpleBackups** configuration files in `mods/simplebackups/configs/`.

> **Restart Required:** Changes to SimpleBackups TOML configuration files require a server restart to take effect.

---

## 1. Configuration Files Overview (`mods/simplebackups/configs/`)

| File | Purpose & Key Settings | Format |
| :--- | :--- | :--- |
| `simplebackups-common.toml` | Core backup schedule, backup type, retention, compression, disk cap, error handling, ignore patterns, and mod compatibility. | TOML |
| `simplebackups-server.toml` | Server-side command permission guard and backup broadcast visibility. | TOML |

---

## 2. `simplebackups-common.toml` Reference

### 2.1 Top-Level Settings
- `enabled` (default `true`): Enables or disables automatic backups. When `false`, no backups are created.
- `backupType` (default `"FULL_BACKUPS"`): Backup strategy. Allowed values:
  - `"FULL_BACKUPS"` — Always creates complete backups.
  - `"MODIFIED_SINCE_LAST"` — Saves only files changed since the last (partial) backup.
  - `"MODIFIED_SINCE_FULL"` — Saves all files changed since the last full backup.
- `saveAll` (default `true`): Forces a `save-all` flush before creating a backup.
- `fullBackupTimer` (default `525960`, range `1..5259600`): Interval in minutes before forcing a full backup when using incremental/modified backup modes (default is once per year).
- `backupsToKeep` (default `10`, range `1..32767`): Maximum number of backup archives retained before oldest backups are pruned.
- `timer` (default `120`, range `1..32767`): Time between backups in minutes (e.g., `5` = every 5 minutes, `60` = hourly, `1440` = daily).
- `compressionLevel` (default `-1`, range `-1..9`):
  - `-1` — Default balanced speed and compression (recommended).
  - `0` — No compression (low CPU usage, larger archives).
  - `9` — Maximum compression (high CPU usage, smaller archives).
- `sendMessages` (default `true`): Broadcasts chat notifications when a backup is in progress.
- `maxDiskSize` (default `"25 GB"`): Maximum total size of the backup folder; older backups are deleted when exceeded. Must follow `<number> <B|KB|MB|GB|TB>`.
- `outputPath` (must remain `"simplebackups"`): Output directory path relative to the server data directory.
- `noPlayerBackups` (default `false`): Creates backups even when no players are online.
- `createSubDirs` (default `false`): Generates per-world subdirectories inside `outputPath`. When `true`, `backupsToKeep` and `maxDiskSize` apply per subdirectory.
- `useTickCounter` (default `false`): Uses an internal tick counter instead of real-world time for `timer`. Server lag (low TPS) increases real-world intervals between backups.

### 2.2 `[error_handling]`
- `collectErrors` (default `true`): Collects I/O errors, prints them to chat, and completes the backup with as many files as possible. When `false`, aborts on the first error.
- `deleteUnfinishedBackup` (default `true`): Deletes failed/incomplete backups immediately when `collectErrors` is `false` so valid backups are not pruned.

### 2.3 `[to_ignore]`
Paths and patterns in this section are relative to the world directory:
- `ignored_paths` (default `[]`): List of directory paths to exclude recursively (e.g., `["logs", "data/cache"]`).
- `ignored_files` (default `[]`): List of specific file paths to exclude (e.g., `["level.dat_old", "stats/player.json"]`).
- `ignored_files_regex` (default `""`): Regular expression matching file paths to exclude (e.g., `".*\\.temp$"`). Leave empty to disable regex exclusion.

### 2.4 `[mod_compat]`
- `mc2discord` (default `true`): Sends backup notifications to Discord via `mc2discord` if installed.
- `onlyFavorites` (default `false`): Limits backups to worlds marked as favorite by the Cherished Worlds mod.

---

## 3. `simplebackups-server.toml` Reference

- `commandsCheatsDisabled` (must remain `false` on multiplayer servers): Allows backup commands to run without cheats/OP permissions. Keep `false` on multiplayer servers so regular players cannot trigger backups.
- `messagesForEveryone` (default `true`): Sends backup status messages to all players when `true`, or restricts them to players with permission level 2+ when `false`.

---

## 4. Mandatory Server Invariants

1. **Relative Output Path (`simplebackups-common.toml`):**
   - `outputPath` **must** remain `"simplebackups"` (relative path inside the server data directory).
2. **Multiplayer Command Guard (`simplebackups-server.toml`):**
   - `commandsCheatsDisabled` **must** remain `false` on multiplayer servers.
3. **Ranges & Enums (`simplebackups-common.toml`):**
   - `backupType` must be one of `FULL_BACKUPS`, `MODIFIED_SINCE_LAST`, or `MODIFIED_SINCE_FULL`.
   - `timer` must be within `1..32767`.
   - `backupsToKeep` must be within `1..32767`.
   - `fullBackupTimer` must be within `1..5259600`.
   - `compressionLevel` must be within `-1..9`.
   - `maxDiskSize` must match `<number> <B|KB|MB|GB|TB>`.
4. **Sanitized Configs Only:**
   - Never place backup archives (`*.zip`, `*.tar`, `*.gz`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`, `*.db`, `*.jar`) or `simplebackups/`, `logs/`, or `world/` directories inside `mods/simplebackups/configs/`.
