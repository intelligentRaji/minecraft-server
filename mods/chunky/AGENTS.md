# Chunky — Configuration Rules (`mods/chunky/`)

## 1. Configuration Scope (`mods/chunky/configs/`)
- Edit Chunky configuration directly inside `mods/chunky/configs/` (`config.json`).
- For schema details, operational notes, and invariants, activate the [`chunky-config` skill](file:///home/wakaria/dev/minecraft-server/mods/chunky/.agents/skills/chunky-config/SKILL.md).

## 2. Server Invariants
1. **Valid Schema & Types (`config.json`):**
   - `version`: integer `>= 1` (currently `2`).
   - `language`: non-empty string (currently `"en"`).
   - `continueOnRestart`: boolean (`false` by default).
   - `forceLoadExistingChunks`: boolean (`false` by default).
   - `silent`: boolean (`false` by default).
   - `updateInterval`: integer `>= 1` (seconds between progress updates; currently `1`).
2. **Live Commands vs. Startup Config:**
   - Execute chunk pre-generation tasks (`/chunky ...`) live via RCON/console rather than editing runtime task files.
   - Changes to `mods/chunky/configs/config.json` require a server restart (or `/chunky reload` if supported, though `config.json` is startup-loaded).

## 3. Sanitized & Excluded Files
- Never place `tasks/` runtime state files (live pre-generation task definitions, progress, coordinates, or timestamps) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/chunky/configs/`.
