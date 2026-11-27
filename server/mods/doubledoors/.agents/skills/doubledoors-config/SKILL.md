---
name: doubledoors-config
description: Inspect and configure Double Doors (1.20.1-7.5, Serilum) static settings—master toggle, recursive multi-block opening and distance limits, door/fence gate/trapdoor toggles, block blacklist, and mod incompatibility checks—in server/mods/doubledoors/configs/config/serilum/doubledoors.json. Use whenever viewing, editing, or validating Double Doors server configuration.
---

# Double Doors Configuration Guide (`doubledoors-config`)

Use this skill to inspect and configure **Double Doors 1.20.1-7.5** (Serilum) in `server/mods/doubledoors/configs/config/serilum/doubledoors.json`.

> **Operational & Restart Notes:**
> - Double Doors settings (especially `"Enable Double Doors"`) are loaded on startup and require restarting **`mc-forge-server`** to take effect.
> - Always obtain **explicit user confirmation** before restarting `mc-forge-server`, and run `list` and `save-all` via RCON if players may be online.
> - When `"Enable Double Doors"` is set to `false`, none of Double Doors' features run and its other settings are hidden in-game.

---

## 1. Configuration File & Serilum JSON Schema

- **Exact file path:** `server/mods/doubledoors/configs/config/serilum/doubledoors.json`
- **Exclusive ownership:** `server/mods/doubledoors/configs/` owns only `config/serilum/doubledoors.json`. Never add `collective.json` or other sibling Serilum configs here.
- **Serilum Collective wrapped JSON format:**
  - **Root object:** May contain an optional `"//"` string comment plus **exactly** the 8 required setting keys (no missing keys, no extra/unknown keys).
  - **Each setting object:** Must contain a `"value"` key and may contain an optional `"//"` string comment (no other keys permitted).
  - **Comments (`"//"`):** Whenever `"//"` is present at root or inside any setting object, its value must be a JSON string.

### Example `config/serilum/doubledoors.json`

```json
{
	"//": "These settings are easier to change in-game! Mod List -> Double Doors -> Config",
	"Enable Double Doors": {
		"//": "Whether Double Doors is enabled. When disabled, none of its features run and its other settings are hidden. Takes effect after a restart.",
		"value": true
	},
	"enableRecursiveOpening": {
		"//": "Whether the recursive opening feature should be enabled. This allows you to for example build a giant door with trapdoors which will all open at the same time, as long as they are connected. The 'recursiveOpeningMaxBlocksDistance' config option determines how far the function should search.",
		"value": true
	},
	"recursiveOpeningMaxBlocksDistance": {
		"//": "How many blocks the recursive function should search when 'enableRecursiveOpening' is enabled. min: 1, max: 64",
		"value": 10
	},
	"enableDoors": {
		"//": "When enables, the mod works with double doors.",
		"value": true
	},
	"enableFenceGates": {
		"//": "When enables, the mod works with double fence gates.",
		"value": false
	},
	"enableTrapdoors": {
		"//": "When enables, the mod works with double trapdoors.",
		"value": false
	},
	"doorBlockBlacklist": {
		"//": "A comma separated list of block ids the mod ignores, so they keep opening one at a time. Works for doors, trapdoors and fence gates. For example 'create:andesite_door,supplementaries:gold_door'.",
		"value": ""
	},
	"enableModIncompatibilityCheck": {
		"//": "Checks if there are other mods loaded with double door functionality, such as Quark. If found, it edits a line in their config to disable double doors. Fixes doors not opening due to code being ran twice.",
		"value": true
	}
}
```

---

## 2. Settings Reference (All 8 Required Keys)

Every key below must remain declared as a Serilum `{ "value": ... }` object in `server/mods/doubledoors/configs/config/serilum/doubledoors.json`.

| Setting Key | Type | Default | Valid Values / Constraints | Description |
| :--- | :--- | :--- | :--- | :--- |
| `"Enable Double Doors"` | `bool` | `true` | Strict JSON `true` or `false` | Master switch for Double Doors. When `false`, none of its features run and its other settings are hidden. Takes effect after a server restart. |
| `"enableRecursiveOpening"` | `bool` | `true` | Strict JSON `true` or `false` | Enables recursive opening for connected multi-block structures (e.g., giant trapdoor doors opening together). Search radius is bounded by `recursiveOpeningMaxBlocksDistance`. |
| `"recursiveOpeningMaxBlocksDistance"` | `int` | `10` | Strict integer `1`–`64` inclusive (no booleans, floats, or strings) | Maximum block search distance when `enableRecursiveOpening` is enabled. Bounded to `1..64` to prevent unbounded recursive block searches from stalling server ticks. |
| `"enableDoors"` | `bool` | `true` | Strict JSON `true` or `false` | Enables double-door behavior for doors. |
| `"enableFenceGates"` | `bool` | `false` | Strict JSON `true` or `false` | Enables double-opening behavior for fence gates. |
| `"enableTrapdoors"` | `bool` | `false` | Strict JSON `true` or `false` | Enables double-opening behavior for trapdoors. |
| `"doorBlockBlacklist"` | `str` | `""` | Empty `""` or comma-separated `namespace:path` IDs matching `^[a-z0-9_.-]+:[a-z0-9_./-]+$` | Comma-separated Minecraft block resource locations ignored by Double Doors (applies to doors, trapdoors, and fence gates) so they open individually. |
| `"enableModIncompatibilityCheck"` | `bool` | `true` | Strict JSON `true` or `false` | Checks for other loaded mods with double-door functionality (e.g., Quark) and disables their conflicting feature in their config so doors do not fail to open from double execution. |

---

## 3. `doorBlockBlacklist` Formatting Rules

`doorBlockBlacklist.value` must be a JSON string following these exact rules:
- **Empty blacklist:** `""` (empty string; whitespace-only strings such as `"   "` are invalid).
- **Non-empty blacklist:** One or more Minecraft block resource locations separated by `,`.
- **Entry pattern:** Every trimmed token must match `^[a-z0-9_.-]+:[a-z0-9_./-]+$` (lowercase `namespace:path` format).
- **No blank or trailing entries:** Leading commas, trailing commas, or consecutive commas (e.g., `"minecraft:oak_door,"` or `"minecraft:oak_door,,create:andesite_door"`) are invalid.
- **No un-namespaced IDs:** Bare block names like `"oak_door"` without a `namespace:` prefix are invalid.

**Valid examples:**
- `""`
- `"create:andesite_door"`
- `"create:andesite_door,supplementaries:gold_door"`
- `"minecraft:iron_door, create:brass_door"`

**Invalid examples:**
- `" "` (whitespace-only)
- `"oak_door"` (missing namespace)
- `"create:andesite_door,"` (trailing comma)
- `"Minecraft:Iron_Door"` (uppercase characters not allowed in resource locations)

---

## 4. Mandatory Invariants & Excluded Files

1. **Exact Schema & Strict Types:**
   - Preserve all 8 required setting keys with exact spelling (note the spaced title-case `"Enable Double Doors"` vs. camelCase for the other 7 keys).
   - Never add extra keys at root or inside any setting object, never use non-string values for `"//"`, and keep `recursiveOpeningMaxBlocksDistance` strictly within `1`–`64`.
2. **Sibling Serilum Isolation:**
   - Never place `collective.json` or any other sibling Serilum mod configs into `server/mods/doubledoors/configs/`.
3. **Excluded Runtime State & Artifacts:**
   - Never place runtime state directories (`logs/`, `mods/`, `playerdata/`, `region/`, `entities/`, `poi/`, `world/`, `data/`, or Serilum runtime data `server/data/data/serilum/` and `server/data/world/data/collective/`), symlinks, or binary/archive/database/lock artifacts (`*.jar`, `*.db`, `*.sqlite`, `*.log`, `*.gz`, `*.zip`, `*.tar`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`) inside `server/mods/doubledoors/configs/`.
4. **Zero Secrets or Credentials:**
   - Never commit passwords, tokens, API keys, webhooks, or private keys (`bottoken`, `webhookurl`, `password`, `secret`, `apikey`, `accesstoken`, `clientsecret`, Discord webhook URLs, Discord bot tokens, PEM private keys) inside `server/mods/doubledoors/configs/`.
