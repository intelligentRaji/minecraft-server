# Just Enough Resources (`jeresources`) — Configuration Rules (`mods/jeresources/`)

## 1. Configuration Scope (`mods/jeresources/configs/`)
- Edit Just Enough Resources (JER) configuration directly inside:
  - `mods/jeresources/configs/config/jeresources-common.toml`
  - `mods/jeresources/configs/config/jeresources.toml`
- For schema details, option descriptions, and operational notes, activate the [`jeresources-config` skill](file:///home/wakaria/dev/minecraft-server/mods/jeresources/.agents/skills/jeresources-config/SKILL.md).

## 2. Server Invariants
1. **Valid Schema & Types (`config/jeresources-common.toml` and `config/jeresources.toml`):**
   - Both files must be valid TOML and contain only the 8 documented top-level keys: `itemsPerColumn`, `itemsPerRow`, `diyData`, `showDevData`, `enchantsBlacklist`, `hiddenTabs`, `dimensionsBlacklist`, and `disableLootManagerReloading`.
   - `itemsPerColumn` and `itemsPerRow` must be integers in the range `1..4` (inclusive).
   - `diyData`, `showDevData`, and `disableLootManagerReloading` must be TOML booleans (`true` or `false`).
   - `enchantsBlacklist` and `hiddenTabs` must be TOML lists of strings.
   - `dimensionsBlacklist` must be a TOML list of integers.
2. **Cross-File Consistency:**
   - Keep `mods/jeresources/configs/config/jeresources-common.toml` and `mods/jeresources/configs/config/jeresources.toml` aligned when modifying shared settings unless an intentional divergence is required.
3. **Startup-Only Application & Restart Discipline:**
   - JER configuration is loaded on server/JEI initialization and is not hot-reloadable.
   - Changes require restarting `mc-forge-server`. Before any restart, obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online.

## 3. Sanitized & Excluded Files
- Never place secrets, symlinks, runtime state directories (`logs/`, `world/`, `mods/`), or binary/archive/database artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/jeresources/configs/`.
