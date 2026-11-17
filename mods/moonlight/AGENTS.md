# Moonlight Lib — Configuration Rules (`mods/moonlight/`)

## 1. Configuration Scope (`mods/moonlight/configs/`)
- Edit Moonlight Lib configuration directly inside `mods/moonlight/configs/`:
  - `config/moonlight-common.toml` — Dynamic resource memory management, multi-threaded asset generation, debug registry dumps, and global datapack folder settings.
- Only `config/moonlight-common.toml` belongs in `mods/moonlight/configs/`.
- For full key schemas, defaults, and operational notes, activate the [`moonlight-config` skill](file:///home/wakaria/dev/minecraft-server/mods/moonlight/.agents/skills/moonlight-config/SKILL.md).

## 2. Server Invariants
1. **Debug Dump Dependency (`extra_children_debug` $\rightarrow$ `extra_debug`):**
   - If `[general].extra_children_debug` is set to `true`, `[general].extra_debug` **must** also be `true` for it to take effect.
   - Keep both `extra_debug` and `extra_children_debug` set to `false` in production unless actively troubleshooting dynamic registry/BlockType issues.
2. **Global Datapacks Path Safety (`global_datapacks_folder`):**
   - `[general].global_datapacks_folder` must be a string containing either `""` (disabled) or a relative path with no leading `/` and no `..` traversal segments (default: `"moonlight-global-datapacks"`).
3. **Startup-Loaded Forge TOML:**
   - `config/moonlight-common.toml` is loaded at startup (not live-reloadable via RCON); changes require a server restart to take effect.

## 3. Excluded Files
- Do not include runtime datapack contents (e.g., `moonlight-global-datapacks/`), debug dumps (`blocktypes_debug.txt`), `logs/`, `world/`, `mods/`, or any credential/secret files in `mods/moonlight/configs/`.
- Never place binary or runtime artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/moonlight/configs/`.
