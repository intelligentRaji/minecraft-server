# ModernFix — Configuration Rules (`mods/modernfix/`)

## 1. Configuration Scope (`mods/modernfix/configs/`)
- Edit ModernFix configuration directly inside `mods/modernfix/configs/` (`modernfix-common.toml` and `modernfix-mixins.properties`).
- For schema details, mixin categories, and operational notes, activate the [`modernfix-config` skill](file:///home/wakaria/dev/minecraft-server/mods/modernfix/.agents/skills/modernfix-config/SKILL.md).

## 2. Server Invariants
1. **Valid Schema & Types (`modernfix-common.toml`):**
   - `blacklist_async_jei_plugins`: TOML array of non-empty strings specifying JEI plugin IDs to load on the main thread (currently `["jepb:jei_plugin"]`).
   - No unexpected keys allowed.
2. **Valid Schema & Overrides (`modernfix-mixins.properties`):**
   - Java `.properties` format where defaults are documented as commented lines (`#  <key>=<value> # (default)`).
   - Add user overrides as uncommented `key=value` lines at the bottom of the file:
     - `mixin.<category>.<name>=true|false` (or `mixin.devenv=true|false`, `mixin.safety=true|false`; categories: `bugfix`, `feature`, `launch`, `perf`).
     - `stability_level=GA|BETA|ALPHA` (default `GA`).
   - No unexpected keys allowed.
3. **Startup-Only Application & Restart Discipline:**
   - ModernFix mixins and common settings are applied at JVM/Forge launch and require a `mc-forge-server` restart to take effect.
   - Before any restart, obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online.

## 3. Sanitized & Excluded Files
- Never place secrets, symlinks, runtime state directories (`logs/`, `world/`, `mods/`), or binary/archive/database artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/modernfix/configs/`.
