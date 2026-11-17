# Create — Configuration Rules (`mods/create/`)

## 1. Configuration Scope (`mods/create/configs/`)
- Edit Create configuration directly inside `mods/create/configs/`:
  - `config/create-common.toml` — Forge common configuration (`[worldgen]` terrain generation toggle).
  - `world/serverconfig/create-server.toml` — world server-side configuration (infrastructure, recipes, kinetics, stress values, contraptions, fluids, logistics, schematics, equipment, and trains).
- For full section/key schemas, value ranges, enum options, and operational notes, activate the [`create-config` skill](file:///home/wakaria/dev/minecraft-server/mods/create/.agents/skills/create-config/SKILL.md).

## 2. Server Invariants
1. **Valid Forge TOML Syntax & Numeric Ranges:**
   - Preserve valid TOML types and keep all numeric values within their Forge comment bounds (e.g., `tickrateSyncTimer > 5`, `maxRotationSpeed > 64`, `crankHungerMultiplier` `0.0 ~ 1.0`, `vaultCapacity` `1 ~ 2048`, `brassTunnelTimer` `1 ~ 10`, `maxSchematicPacketSize` `256 ~ 32767`, `maxTrackPlacementLength` `16 ~ 128`).
   - All stress impact and capacity values under `[kinetics.stressValues.v2.impact]` and `[kinetics.stressValues.v2.capacity]` must be non-negative floats (`>= 0.0`).
2. **Valid Enum Values:**
   - `ignoreDeployerAttacks`: `"ALL"`, `"CREEPERS"`, or `"NONE"`.
   - `movableSpawners`, `amethystMovement`, `movableObsidian`, `movableReinforcedDeepslate`: `"MOVABLE"`, `"NO_PICKUP"`, or `"UNMOVABLE"`.
   - `bottomlessFluidMode`: `"ALLOW_ALL"`, `"DENY_ALL"`, `"ALLOW_BY_TAG"`, or `"DENY_BY_TAG"`.
3. **Reload & Restart Behavior:**
   - `config/create-common.toml` is a startup-only Forge common config; changes take effect on server start/restart.
   - `world/serverconfig/create-server.toml` is a world serverconfig; changes take effect on world/server restart (or via `/create config` / Forge config reload where supported).

## 3. Sanitized & Excluded Files
- Never place runtime world or schematic state (`data/world/schematics/`, `data/world/data/`, `data/world/playerdata/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`, `*.nbt`) inside `mods/create/configs/`.
