---
name: jade-config
description: Inspect and configure Jade server-side plugin overrides and tooltip provider sort-order priorities in mods/jade/configs/.
---

# Jade Configuration Guide (`jade-config`)

Use this skill to inspect and configure **Jade** (`jade`, 1.20.1-Forge-11.13.3) server-side HUD/tooltip inspection settings in `mods/jade/configs/`.

> **Startup-Only Configuration:** Jade server-side settings are loaded during dedicated server initialization and are not hot-reloadable. Edits made in `mods/jade/configs/` require an `mc-forge-server` restart to take effect. Always obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online before restarting.

---

## 1. Configuration File Overview (`mods/jade/configs/`)

On a dedicated Forge server, Jade maintains two JSON configuration files in `mods/jade/configs/`:

| File | Purpose | Format |
| :--- | :--- | :--- |
| `server-plugin-overrides.json` | Maps Jade plugin/provider resource location IDs or option keys to server-enforced override values pushed to connected clients (`ServerPluginConfig`). | JSON object |
| `sort-order.json` | Maps Jade provider resource location IDs to tooltip sort-order priority values (`null` for default priority or a finite numeric priority). | JSON object |

---

## 2. File Schemas & Defaults

### `server-plugin-overrides.json`
- **Root Type:** JSON object (`dict`)
- **Default Value:** `{}` (no server-enforced overrides)
- **Keys:** Non-empty strings representing Jade plugin/provider resource location IDs or option keys (e.g., `"namespace:path"` or `"namespace:path.option"`).
- **Values:** Server-enforced override values (`bool`, finite `int`/`float`, `str`, `null`, or nested `dict`/`list`).

```json
{}
```

When populated, Jade's `ServerPluginConfig` enforces the specified plugin/provider option values on all connected clients regardless of their local client config.

### `sort-order.json`
- **Root Type:** JSON object (`dict`)
- **Keys:** Non-empty strings representing Jade provider resource location IDs (`"namespace:path"`).
- **Values:** `null` (use Jade's default priority) or a finite JSON number (`int` or finite `float`; booleans are not permitted).

Default providers (`20` entries, all mapped to `null`):
- `"jade:object_name"`
- `"minecraft:animal_owner"`
- `"minecraft:beehive"`
- `"minecraft:brewing_stand"`
- `"minecraft:campfire"`
- `"minecraft:chicken_egg"`
- `"minecraft:chiseled_bookshelf"`
- `"minecraft:command_block"`
- `"minecraft:energy_storage"`
- `"minecraft:fluid_storage"`
- `"minecraft:furnace"`
- `"minecraft:item_storage"`
- `"minecraft:jukebox"`
- `"minecraft:lectern"`
- `"minecraft:mob_breeding"`
- `"minecraft:mob_growth"`
- `"minecraft:potion_effects"`
- `"minecraft:progress"`
- `"minecraft:redstone"`
- `"minecraft:zombie_villager"`

---

## 3. Mandatory Server Invariants

1. **Exact Allowed Files:**
   - Only `server-plugin-overrides.json` and `sort-order.json` belong in `mods/jade/configs/`.
2. **Valid JSON & Key Constraints:**
   - Both files must parse as JSON objects (`dict`) with non-empty string keys.
   - `sort-order.json` values must strictly be `null` or finite numbers (`int`/`float`, not `bool`).
   - No credentials, tokens, or secrets may be stored in either file.
3. **Excluded Client-Only Files:**
   - Do NOT add client-only Jade configurations (`jade.json`, `disabled_plugins.json`, `hide-blocks.json`, `hide-entities.json`, `hide-mob-effects.json`, `profiles/`, or `themes/`) to `mods/jade/configs/`.
