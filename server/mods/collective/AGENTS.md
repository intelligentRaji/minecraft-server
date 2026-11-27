# Collective — Configuration Rules (`server/mods/collective/`)

## 1. Configuration Scope (`server/mods/collective/configs/`)
- Edit static Collective configuration directly in `server/mods/collective/configs/config/serilum/collective.json`.
- Only `config/serilum/collective.json` belongs in `server/mods/collective/configs/`.
- For full wrapped JSON schema rules, setting descriptions, translation/resource-pack interactions, TPS tuning, and operational notes, activate the [`collective-config` skill](file:///home/wakaria/dev/minecraft-server/server/mods/collective/.agents/skills/collective-config/SKILL.md).

## 2. Server Invariants
1. **Exact Root & Entry Schema (`collective.json`):**
   - **Root object:** Must declare all 13 documented setting keys plus an optional `"//"` string comment, with no extra or missing keys.
   - **Per-setting entry object:** Each of the 13 setting keys must map to a JSON object with a required `"value"` key and an optional `"//"` string comment, with no extra keys.
2. **Strict Value Invariants (All 13 Settings):**
   - **8 strict booleans (`true` / `false`):**
     - `enableUpdateChecker` (default `true`)
     - `transferItemsBetweenReplacedEntities` (default `true`)
     - `enablePatronPets` (default `true`)
     - `commandsAskForConfirmation` (default `true`)
     - `downloadNonEnglishTranslations` (default `true`)
     - `pushTranslationResourcePack` (default `false`)
     - `requireTranslationResourcePack` (default `true`)
     - `updateMinecraftWindowTitleInDevMode` (default `false`)
   - **2 bounded strict integers:**
     - `findABlockCheckAroundEntitiesDelayMs` — integer in `0`..`3600000` (default `30000`)
     - `configScreenGuiScale` — integer in `0`..`10` (default `0`)
   - **3 strings / enums:**
     - `disabledSerilumMods` — string (`str`, default `""`)
     - `serverLanguage` — non-empty Minecraft locale code matching `^[a-z0-9]+(_[a-z0-9]+)*$` (default `"en_us"`)
     - `itemNameTranslationMode` — one of `"auto"`, `"server"`, or `"client"` (default `"auto"`)
3. **Startup-Only Application & Restart Discipline:**
   - Static changes to `server/mods/collective/configs/config/serilum/collective.json` are startup-only and take effect after restarting `mc-forge-server`.
   - Never restart a running `mc-forge-server` without explicit user confirmation; when players may be online, check `list` and run `save-all` via RCON before any planned restart.

## 3. Sanitized & Excluded Files (Security & Runtime State Isolation)
- **Shared Directory Isolation (`config/serilum/`):** `config/serilum/` is shared on the server with sibling Serilum mods such as `doubledoors.json`. Never add `doubledoors.json` or any other Serilum mod config to `server/mods/collective/configs/`.
- **Excluded Runtime State, Caches & Artifacts:** Never add runtime caches (`cache/`, `data/`, `data/serilum/`), world state (`world/`, `itemnametranslation.txt` from `world/data/collective/itemnametranslation.txt`), server runtime directories (`logs/`, `mods/`, `playerdata/`, `region/`, `entities/`, `poi/`), symlinks, or binary/archive/database/runtime files (`*.jar`, `*.db`, `*.sqlite`, `*.log`, `*.gz`, `*.zip`, `*.tar`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`, `*.dat`, `*.txt`) to `server/mods/collective/configs/`.
- **Zero Secrets:** Never commit secrets, credentials, API tokens, webhooks, passwords, or private keys in `server/mods/collective/configs/`.
