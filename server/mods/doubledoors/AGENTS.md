# Double Doors — Configuration Rules (`server/mods/doubledoors/`)

## 1. Configuration Scope (`server/mods/doubledoors/configs/`)
- Edit static Double Doors (1.20.1-7.5, Serilum) configuration exclusively in `server/mods/doubledoors/configs/config/serilum/doubledoors.json`.
- `server/mods/doubledoors/configs/` owns only `config/serilum/doubledoors.json`; do not place additional config files in this directory.
- For full Serilum Collective JSON schema rules, setting descriptions, blacklist syntax, and examples, activate the [`doubledoors-config` skill](file:///home/wakaria/dev/minecraft-server/server/mods/doubledoors/.agents/skills/doubledoors-config/SKILL.md).

## 2. Schema & Value Invariants
1. **Serilum Collective Wrapped JSON Format (`config/serilum/doubledoors.json`):**
   - Root object may include an optional `"//"` string comment and must declare **exactly** the 8 setting keys below—no missing keys and no extra or unknown keys.
   - Each setting value must be an object containing a required `"value"` key and an optional `"//"` string comment—no other keys are permitted inside setting objects.
   - Wherever `"//"` is present (at root or inside a setting object), its value must be a JSON string.
2. **Required Setting Keys, Types & Constraints:**
   - `"Enable Double Doors"` (`bool`): Strict JSON boolean (`true` or `false`). When `false`, none of Double Doors' features run and its other settings are hidden.
   - `"enableRecursiveOpening"` (`bool`): Strict JSON boolean (`true` or `false`).
   - `"recursiveOpeningMaxBlocksDistance"` (`int`): Strict integer in `1`–`64` inclusive (bounded to prevent unbounded recursive block searches from stalling server ticks).
   - `"enableDoors"` (`bool`): Strict JSON boolean (`true` or `false`).
   - `"enableFenceGates"` (`bool`): Strict JSON boolean (`true` or `false`).
   - `"enableTrapdoors"` (`bool`): Strict JSON boolean (`true` or `false`).
   - `"doorBlockBlacklist"` (`str`): Must be `""` (empty string) or a comma-separated list of Minecraft block resource locations matching `^[a-z0-9_.-]+:[a-z0-9_./-]+$` (no whitespace-only strings, no empty or trailing comma entries, and no un-namespaced block IDs).
   - `"enableModIncompatibilityCheck"` (`bool`): Strict JSON boolean (`true` or `false`).
3. **Startup / Restart Discipline:**
   - Double Doors settings (especially `"Enable Double Doors"`) are loaded on startup and require restarting `mc-forge-server` to take effect.
   - Always obtain explicit user confirmation before restarting `mc-forge-server`, and run `list` and `save-all` via RCON if players may be online.

## 3. Security, Secrets & Runtime State Exclusions
- **Sibling Serilum Isolation:** Never place `collective.json` or any other sibling Serilum mod configs into `server/mods/doubledoors/configs/`; this directory exclusively owns `config/serilum/doubledoors.json`.
- **Excluded Runtime State Directories & Artifacts:** Never place runtime state directories (`logs/`, `mods/`, `playerdata/`, `region/`, `entities/`, `poi/`, `world/`, `data/`, or Serilum runtime data `server/data/data/serilum/` and `server/data/world/data/collective/`), symlinks, or binary/archive/database/lock artifacts (`*.jar`, `*.db`, `*.sqlite`, `*.log`, `*.gz`, `*.zip`, `*.tar`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`) inside `server/mods/doubledoors/configs/`.
- **No Secrets or Credentials:** Never commit passwords, tokens, API keys, webhooks, or private keys (`bottoken`, `webhookurl`, `password`, `secret`, `apikey`, `accesstoken`, `clientsecret`, Discord webhook URLs, Discord bot tokens, PEM private keys) inside `server/mods/doubledoors/configs/`.
