---
name: minecraft-gdrive-sync
description: >-
  Synchronize, upload, and prune Minecraft server mods and backups
  on Google Drive under minecraft-server/mods/.
---

# Minecraft Google Drive Synchronization Runbook

Procedures for keeping Google Drive in sync with local server mods and backups.

---

### Step 1: Synchronize Modpack with Google Drive
To upload all missing local mods and automatically prune any stale/deleted mods from Drive:

```bash
# Preview changes without modifying Drive:
python3 .agents/plugins/minecraft-manager/skills/minecraft-gdrive-sync/scripts/sync_mods_drive.py --dry-run

# Execute full two-way synchronization:
python3 .agents/plugins/minecraft-manager/skills/minecraft-gdrive-sync/scripts/sync_mods_drive.py
```

---

### Step 2: Prune Stale Files from Google Drive
If you only want to clean up remote mods that were removed locally:

```bash
# Preview what would be trashed:
python3 .agents/plugins/minecraft-manager/skills/minecraft-gdrive-sync/scripts/trash_drive.py --prune --dry-run

# Prune stale mods across all categories:
python3 .agents/plugins/minecraft-manager/skills/minecraft-gdrive-sync/scripts/trash_drive.py --prune
```

---

### Step 3: Trash Specific Mod(s) by Filename
To trash specific jar files on Google Drive:

```bash
python3 .agents/plugins/minecraft-manager/skills/minecraft-gdrive-sync/scripts/trash_drive.py <jar_filename> [<jar_filename_2> ...]
```

---

### Invariants & In-Game Safety
* **Zero Drift:** Always run `sync_mods_drive.py` after any mod additions, removals, or upgrades.
* **Non-Destructive Trashing:** Files are moved to Google Drive Trash (recoverable) rather than permanently purged.
