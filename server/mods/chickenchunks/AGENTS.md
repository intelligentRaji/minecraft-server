# ChickenChunks — Configuration Rules (`server/mods/chickenchunks/`)

## 1. Configuration Scope (`server/mods/chickenchunks/configs/`)
- Edit static ChickenChunks configuration directly in `server/mods/chickenchunks/configs/ChickenChunks.cfg`.
- Only `ChickenChunks.cfg` belongs in `server/mods/chickenchunks/configs/` (ChickenChunks has no separate CodeChickenLib config file).
- For full CodeChickenLib `.cfg` syntax rules, key reference, defaults, and operational notes, activate the [`chickenchunks-config` skill](file:///home/wakaria/dev/minecraft-server/server/mods/chickenchunks/.agents/skills/chickenchunks-config/SKILL.md).

## 2. Schema & Value Invariants
1. **CodeChickenLib `.cfg` Syntax (`ChickenChunks.cfg`):**
   - Uses `#` comments and typed top-level entries: `B:"<key>"=<bool>` for booleans and `I:"<key>"=<int>` for integers (no TOML sections or JSON).
2. **Required Static Keys, Exact Types & Server Policy Invariants:**
   - All 6 static keys must be present with exact type prefixes, no duplicate keys, and no unexpected keys or `{ ... }` blocks:
     - `B:"opsBypassRestrictions"` — must be `false` (OPs remain subject to server chunkloading caps)
     - `B:"opsAccessAllLoaders"` — strict boolean (`true` or `false`, default `true`)
     - `B:"allowOffline"` — must be `false` (chunks unload when the owner is offline)
     - `I:"offlineTimeout"` — integer in `0..60` minutes (default `0`)
     - `I:"totalAllowedChunks"` — integer in `1..25` (default `25`)
     - `I:"chunksPerLoader"` — integer in `1..25` and `<= totalAllowedChunks` (default `25`)
3. **Startup / Restart Behavior:**
   - Static changes to `server/mods/chickenchunks/configs/ChickenChunks.cfg` take effect on `mc-forge-server` startup; coordinate with server restart rules if `mc-forge-server` is currently running.

## 3. Security, Secrets & Runtime State Exclusions
- **Mixed-File Runtime Isolation (`"playerRestrictions"`):** Never add a `"playerRestrictions" { ... }` block or key (nor its `# Specifies restrictions for each player...` runtime block) to `server/mods/chickenchunks/configs/ChickenChunks.cfg`. Per-player UUID chunkloader overrides are managed live in-game via `/chickenchunks restrict player ...` and belong exclusively to live server runtime state.
- **Excluded Runtime Directories & Files:** Never add `chickenchunks/` (e.g., `world/chickenchunks/` per-dimension chunkloader state), `world/`, `loginTimes.dat`, `data/`, `libs/`, `logs/`, symlinks, or binary/database/runtime/archive files (`*.dat`, `*.jar`, `*.db`, `*.sqlite`, `*.log`, `*.gz`, `*.zip`, `*.tar`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`) to `server/mods/chickenchunks/configs/`.
- **Zero Secrets:** Never commit credentials, tokens, webhooks, passwords, or private keys in `server/mods/chickenchunks/configs/`.
