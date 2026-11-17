# Every Compat (Wood Good) — Configuration Rules (`mods/everycomp/`)

## 1. Configuration Scope (`mods/everycomp/configs/`)
- Edit Every Compat (Wood Good) configuration directly inside `mods/everycomp/configs/`:
  - `config/everycomp-common.toml` — General asset generation, creative tab placement, blocktype tag generation, debug/version-check packets, and item tooltip settings.
  - `config/everycomp-entries.toml` — Safe recipe and creative-tab toggles for wood types, leaf types, and supported mod entry sets (does not alter block/item registration).
  - `config/everycomp-hazardous.toml` — Conditional block/item registration blacklists (`[woodtype]`, `[leavestype]`, `[block]`, `[entryset]`, `[module]`) and `[other].include_all_wood_modules`.
- For full section/key schemas, regex formats, and operational notes, activate the [`everycomp-config` skill](file:///home/wakaria/dev/minecraft-server/mods/everycomp/.agents/skills/everycomp-config/SKILL.md).

## 2. Server Invariants
1. **Critical Client-Server Parity (`everycomp-hazardous.toml`):**
   - `config/everycomp-hazardous.toml` controls conditional block/item registration. Any change to `[woodtype].blacklist`, `[leavestype].blacklist`, `[block].blacklist`, `[entryset].blacklist`, `[module].blacklist`, or `[other].include_all_wood_modules` on the server **must** be mirrored identically on all clients; otherwise players will fail to join due to registry mismatches.
   - All blacklist entries must be valid non-empty regex strings.
2. **Safe Toggles vs. Registration (`everycomp-entries.toml`):**
   - Use `config/everycomp-entries.toml` to hide items from creative tabs and disable their recipes without breaking client-server registry parity. All leaf keys must be booleans (`true` or `false`).
3. **Production & Startup Discipline (`everycomp-common.toml`):**
   - Keep `[general].generate_dynamic_assets = true` unless all generated assets are supplied manually via datapack.
   - Keep `[general].save_debug_resources = false` and `[general].debug_packet = false` in production.
   - All three Forge TOML configs are startup-loaded (not live-reloadable via RCON); changes require a server restart to take effect.

## 3. Excluded Files
- Do not include generated debug resource dumps, `logs/`, `world/`, `mods/`, or any credential/secret files in `mods/everycomp/configs/`.
- Never place binary or runtime artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/everycomp/configs/`.
