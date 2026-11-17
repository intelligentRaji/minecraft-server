# Paradigm Essentials — Configuration Rules (`mods/paradigm/`)

## 1. Configuration Scope (`mods/paradigm/configs/`)
- Edit Paradigm Essentials settings directly inside `mods/paradigm/configs/`.
- For module descriptions, schema conventions, formatting tags, and placeholders, activate the [`paradigm-config` skill](file:///home/wakaria/dev/minecraft-server/mods/paradigm/.agents/skills/paradigm-config/SKILL.md).

## 2. Server Invariants
1. **LuckPerms Single Source of Truth (`main.json`):**
   - `internalPermissionsEnable.value` **must** remain `false` so Paradigm resolves permissions and `{prefix}` / `{suffix}` metadata from LuckPerms rather than its internal database.
2. **Uniform Prefix, Name & Clan Suffix Coloring (`chat.json` & `tablist.json`):**
   - `chat.json` $\rightarrow$ `customChatFormat.value` **must** contain `{prefix}{player_name}{suffix}` (without wrapping `{prefix}` or `{suffix}` in outer `<color:...>` tags).
   - `tablist.json` $\rightarrow$ `playerFormat.value` **must** contain `{prefix}{player_name}{suffix}`.

## 3. Sanitized & Excluded Files
- `mods/paradigm/configs/cooldowns.json` must contain **only** `"commandCooldownSeconds"` and `"commandWarmupSeconds"` (never add `"cooldowns"` player UUID timestamps).
- `mods/paradigm/configs/holograms.json` must contain **only** `"enabled"`, `"defaultViewDistance"`, `"defaultRefreshIntervalSeconds"`, and `"renderMode"` (never add `"holograms"` in-world coordinate definitions).
- Never add `discord.json`, `storage.json`, `discovered_permissions.json`, `data/`, `libs/`, `icons/`, or `menus/` to `mods/paradigm/configs/`.
