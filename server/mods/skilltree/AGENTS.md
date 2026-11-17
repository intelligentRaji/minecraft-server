# Passive Skill Tree — Configuration Rules (`mods/skilltree/`)

## 1. Configuration Scope (`mods/skilltree/configs/`)
- Edit Passive Skill Tree configuration directly inside `mods/skilltree/configs/`:
  - `skilltree-common.toml` — shared Forge common configuration (skill points, gem drops, equipment sockets, amnesia scroll, grindstone XP, and mixtures).
  - `skilltree-server.toml` — world/server-side overrides for skill points, amnesia scroll, and grindstone XP.
- For full section/key schemas, value ranges, and operational notes, activate the [`skilltree-config` skill](file:///home/wakaria/dev/minecraft-server/mods/skilltree/.agents/skills/skilltree-config/SKILL.md).

## 2. Server Invariants
1. **Valid Forge TOML Syntax & Ranges:**
   - All numeric values must stay within their Forge TOML comment ranges (e.g., `"Maximum skill points"` `1 ~ 1000` in `skilltree-common.toml` and `> 1` in `skilltree-server.toml`, multipliers `0.0 ~ 1.0` or `0.0 ~ 2.0`, socket counts `0 ~ 4`).
   - Preserve exact quoted TOML key names, including `"Enable exprerience exchange for skill points"` (with `exprerience`).
2. **`"Levelup costs"` Array Length Invariant:**
   - In both `skilltree-common.toml` and `skilltree-server.toml`, the `"Levelup costs"` integer array length **must** equal `"Maximum skill points"` (85 entries in `skilltree-common.toml`, 100 entries in `skilltree-server.toml` by default), with all elements `> 0`.
3. **Server Override Precedence & Restart Behavior:**
   - Both files are startup-only Forge TOML configs; changes take effect on server start/restart.
   - `skilltree-server.toml` overrides server-side `["Skill Points"]`, `["Amnesia Scroll"]`, and `[Experience]` settings for the world. Keep `skilltree-common.toml` and `skilltree-server.toml` aligned when tuning those shared sections so client UI and server progression stay consistent.

## 3. Sanitized & Excluded Files
- Never place runtime or player state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/skilltree/configs/`.
