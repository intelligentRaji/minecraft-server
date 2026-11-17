# FerriteCore — Configuration Rules (`mods/ferritecore/`)

## 1. Configuration Scope (`mods/ferritecore/configs/`)
- Edit FerriteCore configuration directly inside `mods/ferritecore/configs/config/ferritecore-mixin.toml`.
- For schema details, option descriptions, and operational notes, activate the [`ferritecore-config` skill](file:///home/wakaria/dev/minecraft-server/mods/ferritecore/.agents/skills/ferritecore-config/SKILL.md).

## 2. Server Invariants
1. **Valid Schema & Types (`config/ferritecore-mixin.toml`):**
   - Must be valid TOML containing only the 11 boolean mixin options: `compactFastMap`, `useSmallThreadingDetector`, `cacheMultipartPredicates`, `multipartDeduplication`, `blockstateCacheDeduplication`, `modelResourceLocations`, `modelSides`, `replaceNeighborLookup`, `populateNeighborTable`, `replacePropertyMap`, and `bakedQuadDeduplication`.
   - Every option value must be a TOML boolean (`true` or `false`); no unexpected keys allowed.
2. **Option Dependency Invariants:**
   - `multipartDeduplication = true` requires `cacheMultipartPredicates = true`.
   - `replacePropertyMap = true` requires `replaceNeighborLookup = true`.
3. **Startup-Only Application & Restart Discipline:**
   - FerriteCore mixin options are applied during JVM/Forge mixin bootstrap on server start and are not hot-reloadable.
   - Changes require restarting `mc-forge-server`. Before any restart, obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online.

## 3. Sanitized & Excluded Files
- Never place secrets, symlinks, runtime state directories (`logs/`, `world/`, `mods/`), or binary/archive/database artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/ferritecore/configs/`.
