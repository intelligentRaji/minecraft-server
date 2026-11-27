---
name: collective-config
description: Inspect and configure Collective (Serilum library mod for Forge 1.20.1) settings in server/mods/collective/configs/config/serilum/collective.json, including disabled Serilum mods, entity/block check delays, command confirmations, server language, and translation resource pack behavior. Use whenever viewing, modifying, or validating Collective configuration.
---

# Collective Configuration Guide (`collective-config`)

Use this skill to inspect and modify **Collective 1.20.1-8.88** static server configuration in `server/mods/collective/configs/config/serilum/collective.json`.

> **Operational & Restart Notes:**
> - Collective reads `config/serilum/collective.json` on startup. Edits to `server/mods/collective/configs/config/serilum/collective.json` require restarting `mc-forge-server` to take effect.
> - Obtain explicit user confirmation before restarting a running `mc-forge-server`. If players may be online, run `list` and `save-all` via RCON first.

---

## 1. Configuration File & Wrapped JSON Schema

- **Exact file path:** `server/mods/collective/configs/config/serilum/collective.json`
- **Shared directory note:** `config/serilum/` is shared with sibling Serilum mods (such as `doubledoors.json`). Only `collective.json` belongs inside `server/mods/collective/configs/config/serilum/`.
- **Serilum wrapped JSON format:**
  - **Root object:** Must contain all 13 setting keys listed in Section 2 plus an optional `"//"` string comment describing the file. No extra keys or missing setting keys are permitted.
  - **Per-setting entry object:** Each of the 13 settings must be a JSON object with:
    - `"value"` *(required)*: The typed setting value.
    - `"//"` *(optional)*: A string comment documenting the option.
    - No other keys are permitted inside a setting object.

---

## 2. Settings Reference (`collective.json`)

All 13 settings below must remain present in `server/mods/collective/configs/config/serilum/collective.json`.

| Setting Key | Type | Valid Values / Constraint | Default | Behavior |
| :--- | :--- | :--- | :--- | :--- |
| `disabledSerilumMods` | `string` | Any string (comma-separated/list format managed by Collective) | `""` | Serilum mods turned off from the installed set. Mirrors each mod's own `'Enable'` setting. Takes effect after restart. |
| `enableUpdateChecker` | `boolean` | `true` or `false` | `true` | Logs an optional async console notice when a dependent Serilum mod has an update available. |
| `transferItemsBetweenReplacedEntities` | `boolean` | `true` or `false` | `true` | Transfers held items and armor from replaced entities spawned by Entity Spawn mods that depend on Collective. |
| `findABlockCheckAroundEntitiesDelayMs` | `integer` | `0` to `3600000` (inclusive) | `30000` | Delay in milliseconds between around-entity blockstate checks for dependent mods. Raising this value reduces check frequency and can improve TPS; lowering it increases responsiveness at higher TPS cost. |
| `enablePatronPets` | `boolean` | `true` or `false` | `true` | Enables pets for Patrons (reserved for a future Collective release). |
| `commandsAskForConfirmation` | `boolean` | `true` or `false` | `true` | Prompts players to click `[Confirm]` before executing Serilum commands that overwrite or alter many blocks/settings at once. |
| `downloadNonEnglishTranslations` | `boolean` | `true` or `false` | `true` | Allows Collective to download non-English translations (from `https://github.com/Serilum/.translations` via `https://translations.serilum.com/`, hosted on CloudFlare Pages) when a non-English language is used. |
| `pushTranslationResourcePack` | `boolean` | `true` or `false` | `false` | On a server, sends connecting players who lack Collective a generated resource pack so custom item names from server-side Serilum mods render in their own client language. |
| `requireTranslationResourcePack` | `boolean` | `true` or `false` | `true` | Marks the pushed translation resource pack as required, so declining kicks the player and re-prompts on next join instead of remembering the decline permanently. Set to `false` to make it optional. |
| `serverLanguage` | `string` | Non-empty lowercase locale matching `^[a-z0-9]+(_[a-z0-9]+)*$` | `"en_us"` | Minecraft locale code (e.g., `"en_us"`, `"de_de"`, `"fr_fr"`) used for Serilum mod text shown to players without Collective who are not sent the translation resource pack. |
| `itemNameTranslationMode` | `string` | `"auto"`, `"server"`, or `"client"` | `"auto"` | Controls custom item name rendering for players without Collective when `pushTranslationResourcePack` is `false` (see Section 3). |
| `configScreenGuiScale` | `integer` | `0` to `10` (inclusive) | `0` | GUI scale for Serilum mod config screens (`0` uses the client's own GUI scale). |
| `updateMinecraftWindowTitleInDevMode` | `boolean` | `true` or `false` | `false` | Local IDE development helper only; has no effect on a production server. |

---

## 3. Translation, Resource Pack & TPS Behavior

### Translation & Resource Pack Pipeline
The 5 localization settings interact as follows:
1. **`downloadNonEnglishTranslations`** (`true` by default) controls whether Collective fetches non-English locale files from Serilum's translation endpoint when needed.
2. **When `pushTranslationResourcePack` is `true`:**
   - Connecting players without Collective are sent a resource pack so custom Serilum item names render in each player's own client language.
   - `requireTranslationResourcePack` (`true` by default) enforces acceptance by kicking on decline so the prompt appears again on reconnect rather than permanently storing a decline.
3. **When `pushTranslationResourcePack` is `false` (default):**
   - No translation resource pack is pushed; `itemNameTranslationMode` and `serverLanguage` govern what players without Collective see:
     - `"auto"` *(default)*: Copies the locale of the first player to join and remembers it across joins.
     - `"server"`: Always uses `serverLanguage` (must match `^[a-z0-9]+(_[a-z0-9]+)*$`, e.g., `"en_us"`).
     - `"client"`: Attempts to use each player's own client language, though players without Collective will see raw translation keys.

### TPS Tuning (`findABlockCheckAroundEntitiesDelayMs`)
- Dependent Serilum mods that check for specific blockstates around entities run periodic scans governed by `findABlockCheckAroundEntitiesDelayMs` (default `30000` ms = 30 seconds).
- Keep this within `0`..`3600000` (max 1 hour). Very low values (near `0`) can degrade server TPS when many entities are loaded; increasing the delay reduces entity-scan overhead.

---

## 4. Reference `collective.json` Example

```json
{
	"//": "These settings are easier to change in-game! Mod List -> Collective -> Config",
	"disabledSerilumMods": {
		"//": "The Serilum mods that are turned off, picked from the ones installed. A mod's own 'Enable' setting follows this list, and the other way round. Takes effect after a restart.",
		"value": ""
	},
	"enableUpdateChecker": {
		"//": "Whether Collective should show a message in the console if a dependent mod has an update available. Update checks are optional and async.",
		"value": true
	},
	"transferItemsBetweenReplacedEntities": {
		"//": "When enabled, transfer the held items and armour from replaced entities by any of the Entity Spawn mods which depend on Collective.",
		"value": true
	},
	"findABlockCheckAroundEntitiesDelayMs": {
		"//": "The delay of the is-there-a-block-around-check around entities in ms. Used in mods which depends on a specific blockstate in the world. Increasing this number can increase TPS if needed. min: 0, max: 3,600,000",
		"value": 30000
	},
	"enablePatronPets": {
		"//": "Enables pets for Patrons. Will be added in a future release.",
		"value": true
	},
	"commandsAskForConfirmation": {
		"//": "Whether commands of Serilum's mods that overwrite or change a lot at once first ask you to click [Confirm].",
		"value": true
	},
	"downloadNonEnglishTranslations": {
		"//": "Whether Collective should attempt to download translations if the client language is set to something other than English. Uses files from https://github.com/Serilum/.translations, downloaded via https://translations.serilum.com/. Hosted via CloudFlare Pages.",
		"value": true
	},
	"pushTranslationResourcePack": {
		"//": "On a server, sends connecting players without Collective a resource pack so custom item names from server-side Serilum mods show up in their own language. Off by default; without it they see the server language instead (see serverLanguage).",
		"value": false
	},
	"requireTranslationResourcePack": {
		"//": "Marks the resource pack as required, so an accidental decline only kicks the player and asks again next join instead of being remembered for good. Turn off to make it optional.",
		"value": true
	},
	"serverLanguage": {
		"//": "The language Serilum mod text shows in for players without Collective who aren't sent the resource pack. Uses locale codes like en_us or de_de.",
		"value": "en_us"
	},
	"itemNameTranslationMode": {
		"//": "How custom item names show for players without Collective when the resource pack is off. 'auto' copies the first player to join and remembers it; 'server' always uses the server language; 'client' uses each player's own language, but those without Collective then see raw keys. options: auto, server, client",
		"value": "auto"
	},
	"configScreenGuiScale": {
		"//": "The GUI scale of the config screens of Serilum's mods, also set with the button next to the ? on those screens. 0 uses the game's own GUI scale. min: 0, max: 10",
		"value": 0
	},
	"updateMinecraftWindowTitleInDevMode": {
		"//": "Used in my local development flow. Has no effect in production, only when ran from an IDE with Collective installed.",
		"value": false
	}
}
```

---

## 5. Mandatory Invariants & Excluded Files

1. **Exact Schema & Strict Types:**
   - Keep all 13 keys present in `collective.json`, each as `{"value": ...}` with optional `"//"` string comment.
   - Use strict JSON booleans (`true`/`false` — never strings or `0`/`1`) for the 8 boolean settings, strict integers within bounds (`0`..`3600000` and `0`..`10` — never floats or booleans) for the 2 integer settings, a string for `disabledSerilumMods`, a valid `^[a-z0-9]+(_[a-z0-9]+)*$` locale code for `serverLanguage`, and `"auto"`, `"server"`, or `"client"` for `itemNameTranslationMode`.
2. **Shared Directory Isolation (`config/serilum/`):**
   - Never add sibling Serilum mod configs such as `doubledoors.json` to `server/mods/collective/configs/`.
3. **Excluded Runtime State, Caches & Artifacts:**
   - Never add `cache/`, `data/`, `data/serilum/`, `world/`, `itemnametranslation.txt` (from `world/data/collective/itemnametranslation.txt`), `logs/`, `mods/`, `playerdata/`, `region/`, `entities/`, `poi/`, symlinks, or binary/archive/database/runtime files (`*.jar`, `*.db`, `*.sqlite`, `*.log`, `*.gz`, `*.zip`, `*.tar`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`, `*.dat`, `*.txt`) to `server/mods/collective/configs/`.
4. **Zero Secrets:**
   - Never commit secrets, credentials, API tokens, webhooks, passwords, or private keys in `server/mods/collective/configs/`.
