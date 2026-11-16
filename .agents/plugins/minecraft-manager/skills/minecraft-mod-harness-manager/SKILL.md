---
name: minecraft-mod-harness-manager
description: >-
  Create, audit, and remove per-mod config folders (mods/<slug>/) and their
  AI skill harnesses (.agents/skills/<slug>-config/), keeping root
  .agents/skills.json synchronized whenever mods are installed or removed.
---

# Minecraft Mod Harness Lifecycle Runbook

Step-by-step procedure for scaffolding or deleting a mod's vertical slice directory (`mods/<slug>/`) whenever a server mod is installed into or removed from `modpack/`.

---

### Step 1: Audit Unmapped Runtime Configs
After installing and booting a server with a new mod, detect newly generated config files in `data/config/` and `data/world/serverconfig/` that are not yet owned by any `mods/<slug>/` folder:

```bash
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-harness-manager/scripts/audit_unmapped.py
```
*(Or run `make config-unmapped`.)*

---

### Step 2: Create a Mod Folder & Skill Harness (On Mod Install)
1. Inspect the unmapped files under `data/` and separate **safe server configs** (`--map`) from **secrets, databases, or player PII** (`--forbid`).
2. Run `create_mod_harness.py` (preview with `--dry-run` first):

```bash
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-harness-manager/scripts/create_mod_harness.py <slug> \
  --map <local_name>:<data_rel_path> \
  --forbid <sensitive_data_rel_path> \
  --dry-run
```

This generates:
- `mods/<slug>/configs/` (populated via `sync_config.py pull` after secret scanning)
- `mods/<slug>/.agents/skills/<slug>-config/SKILL.md`
- `mods/<slug>/.agents/skills/<slug>-config/scripts/sync_config.py`
- A `"mods/<slug>/.agents/skills"` entry in root `.agents/skills.json`

3. Confirm zero unmapped configs and zero drift:
   - `make config-unmapped`
   - `make config-diff`

---

### Step 3: Remove a Mod Folder & Skill Harness (On Mod Removal)
When a mod is uninstalled from `modpack/`, remove its `mods/<slug>/` directory and unregister its skill from `.agents/skills.json` (pass `--prune-data` if you also want mapped config files deleted from `data/`):

```bash
# Preview removal:
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-harness-manager/scripts/remove_mod_harness.py <slug> --dry-run

# Remove mod slice and unregister skill:
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-harness-manager/scripts/remove_mod_harness.py <slug>
```
