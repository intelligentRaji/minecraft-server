---
name: moonlight-config
description: Inspect and configure Moonlight Lib common settings (dynamic resource clearing, multi-threaded asset generation, debug registry dumps, and global datapacks folder) in mods/moonlight/configs/.
---

# Moonlight Lib Configuration Guide (`moonlight-config`)

Use this skill to inspect and modify **Moonlight Lib** configuration in `mods/moonlight/configs/`.

> **Startup Forge TOML Config:** `config/moonlight-common.toml` is loaded at startup and is not live-reloadable via RCON; changes require a server restart to take effect.

---

## 1. Configuration File Overview (`mods/moonlight/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/moonlight-common.toml` | Common settings for dynamic resource memory cleanup, multi-threaded asset generation, debug registry dumps, and global datapack loading. | TOML |

Only `config/moonlight-common.toml` belongs in `mods/moonlight/configs/`.

---

## 2. `config/moonlight-common.toml` Reference

### `[general]`
- `clear_dynamic_resources` (boolean, default `false`): Clears dynamic models and textures from the mod dynamic pack once resource reload is done to save RAM. Turn off (`false`) if resource pack loading inconsistencies occur.
- `multi_threaded_generation` (boolean, default `true`): Enables multi-threaded generation for dynamic assets (if supported) to improve performance on multi-core systems.
- `extra_debug` (boolean, default `false`): Debug-only toggle enabling extra logging and `blocktypes_debug.txt` (`dynamic_registry_dump`). Keep `false` in production unless troubleshooting.
- `extra_children_debug` (boolean, default `false`): Lists each `BlockType`'s children in the same debug dump file (`blocktypes_debug.txt`). **Requires `extra_debug = true` to take effect.**
- `global_datapacks_folder` (string, default `"moonlight-global-datapacks"`): Relative folder path for loading global datapacks across all worlds automatically. Set to `""` (empty string) to disable.

---

## 3. Mandatory Invariants

1. **Single Config File Scope:**
   - Only `config/moonlight-common.toml` belongs in `mods/moonlight/configs/`.
2. **Debug Flag Coupling:**
   - If `extra_children_debug = true`, then `extra_debug` **must** also be `true`.
   - Keep `extra_debug = false` and `extra_children_debug = false` in production unless actively debugging.
3. **Relative Path Constraint (`global_datapacks_folder`):**
   - `global_datapacks_folder` must be a string containing either `""` (to disable) or a relative path—never a leading `/` and never any `..` traversal segments.
4. **Restart Discipline:**
   - `config/moonlight-common.toml` is a startup-loaded Forge TOML file; restart the server after making changes.
5. **Excluded Files & Runtime State:**
   - Never place runtime datapack contents (e.g., `moonlight-global-datapacks/`), debug dumps (`blocktypes_debug.txt`), `logs/`, `world/`, `mods/`, or any credential/secret files in `mods/moonlight/configs/`.
   - Never place binary or runtime artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/moonlight/configs/`.
