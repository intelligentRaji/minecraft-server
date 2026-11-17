# Jade (`jade`) — Configuration Rules (`mods/jade/`)

## 1. Configuration Scope (`mods/jade/configs/`)
- Edit Jade server-side configuration directly inside:
  - `mods/jade/configs/server-plugin-overrides.json` (server-enforced plugin/provider config overrides pushed to connected clients)
  - `mods/jade/configs/sort-order.json` (server-side provider tooltip sort-order priorities)
- For schema details, provider IDs, and operational notes, activate the [`jade-config` skill](file:///home/wakaria/dev/minecraft-server/mods/jade/.agents/skills/jade-config/SKILL.md).

## 2. Server Invariants
1. **Allowed Files Only:**
   - Only `server-plugin-overrides.json` and `sort-order.json` may exist inside `mods/jade/configs/`.
2. **Valid JSON & Key Format:**
   - Both files must be valid UTF-8 JSON objects (`{...}`).
   - All keys in both files must be non-empty strings (typically Jade plugin/provider resource location IDs such as `"namespace:path"` or option keys such as `"namespace:path.option"`).
3. **`sort-order.json` Value Constraints:**
   - Every value in `sort-order.json` must be `null` (default priority) or a finite JSON number (`int` or finite `float`, never a boolean).
4. **Startup-Only Application & Restart Discipline:**
   - Jade server configurations are loaded during server initialization; they are not hot-reloadable.
   - Any changes require restarting `mc-forge-server`. Before any restart, obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online.

## 3. Sanitized & Excluded Files
- Never place client-only Jade configurations (`jade.json`, `disabled_plugins.json`, `hide-blocks.json`, `hide-entities.json`, `hide-mob-effects.json`, `profiles/`, `themes/`), credentials/secrets, symlinks, or binary/archive/database artifacts inside `mods/jade/configs/`.
