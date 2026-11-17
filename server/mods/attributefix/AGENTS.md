# AttributeFix — Configuration Rules (`mods/attributefix/`)

## 1. Configuration Scope (`mods/attributefix/configs/`)
- Edit AttributeFix configuration directly inside `mods/attributefix/configs/attributefix.json`.
- For schema details, active attribute overrides, and operational notes, activate the [`attributefix-config` skill](file:///home/wakaria/dev/minecraft-server/mods/attributefix/.agents/skills/attributefix-config/SKILL.md).

## 2. Server Invariants
1. **Valid JSON & Top-Level Schema (`attributefix.json`):**
   - Must be valid JSON with a single top-level key `"attributes"` mapping `<namespace>:<path>` attribute IDs (non-empty strings) to attribute entries.
   - No extra top-level keys are permitted.
2. **Attribute Entry Schema & Bounds:**
   - Every attribute entry must define `"enabled"` as a strict JSON boolean (`true` or `false`).
   - `"min"` and `"max"` must each be objects containing `"default"` and `"value"` as finite numbers (not booleans or strings).
   - Bounds must satisfy `min.default <= max.default` and `min.value <= max.value`.
3. **Startup-Only Application & Restart Discipline:**
   - AttributeFix reads `attributefix.json` on server startup and does not support hot-reloading.
   - Changes require restarting `mc-forge-server`. Before any restart, obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online.

## 3. Sanitized & Excluded Files
- Never place secrets, credentials, symlinks, runtime state directories (`logs/`, `world/`, `mods/`), or binary/archive/database artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/attributefix/configs/`.
