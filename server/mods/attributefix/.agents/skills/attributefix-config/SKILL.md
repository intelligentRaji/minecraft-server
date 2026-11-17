---
name: attributefix-config
description: Inspect and configure AttributeFix attribute clamp bounds (vanilla, Forge, SkillTree, and Botania attribute min/max overrides) in mods/attributefix/configs/.
---

# AttributeFix Configuration Guide (`attributefix-config`)

Use this skill to inspect and modify **AttributeFix** configuration in `mods/attributefix/configs/`.

> **Startup-Only Configuration:** AttributeFix loads `attributefix.json` during server startup and does not hot-reload at runtime. Any edits to `mods/attributefix/configs/attributefix.json` require restarting `mc-forge-server` to take effect. Always obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online before restarting.

---

## 1. Configuration File Overview (`mods/attributefix/configs/`)

| File | Purpose | Format |
| :--- | :--- | :--- |
| `attributefix.json` | Defines per-attribute enablement and minimum/maximum clamp bounds for vanilla Minecraft, Forge, and modded attributes. | JSON |

---

## 2. `attributefix.json` Schema

The file is a JSON object with a single top-level key `"attributes"` mapping `<namespace>:<path>` attribute IDs to entry objects:

```json
{
  "attributes": {
    "minecraft:generic.max_health": {
      "enabled": true,
      "min": {
        "default": 1,
        "value": 1
      },
      "max": {
        "default": 1024,
        "value": 1000000
      }
    }
  }
}
```

### Field Reference

| Field | Type | Description |
| :--- | :--- | :--- |
| `<namespace>:<path>` | `string` | Non-empty attribute resource location (e.g. `minecraft:generic.max_health`, `forge:entity_reach`, `skilltree:evasion`). |
| `enabled` | `boolean` | When `true`, AttributeFix overrides the attribute's clamp bounds with `min.value` and `max.value`. When `false`, the entry is left at vanilla/mod defaults. |
| `min.default` | `number` | Baseline minimum bound reported by vanilla or the owning mod (informational reference). |
| `min.value` | `number` | Active minimum clamp bound applied when `enabled` is `true`. |
| `max.default` | `number` | Baseline maximum bound reported by vanilla or the owning mod (informational reference). |
| `max.value` | `number` | Active maximum clamp bound applied when `enabled` is `true`. |

---

## 3. Notable Active Overrides & Configured Namespaces

### Raised Vanilla Caps (`enabled: true`)

These vanilla attributes have their maximum clamp raised above baseline to prevent high-tier gear, enchantments, or SkillTree bonuses from hitting vanilla caps:

| Attribute ID | `min.value` | `max.default` | `max.value` |
| :--- | :--- | :--- | :--- |
| `minecraft:generic.max_health` | `1` | `1024` | `1000000` |
| `minecraft:generic.armor` | `0` | `30` | `1000000` |
| `minecraft:generic.armor_toughness` | `0` | `20` | `1000000` |
| `minecraft:generic.attack_damage` | `0` | `2048` | `1000000` |
| `minecraft:generic.attack_knockback` | `0` | `5` | `1000000` |

### Other Configured Attributes

- **`minecraft:*` (`enabled: true`, matching defaults):** `generic.follow_range` (`0..2048`), `generic.attack_speed` (`0..1024`), `generic.luck` (`-1024..1024`), `air_drag_modifier` (`0..2048`), `waypoint_receive_range` (`0..60000000`), `waypoint_transmit_range` (`0..60000000`), `generic.flying_speed` (`0..1024`), `generic.movement_speed` (`0..1024`), `bounciness` (`0..1`), `friction_modifier` (`0..2048`), `zombie.spawn_reinforcements` (`0..1`), `horse.jump_strength` (`0..2`), `generic.knockback_resistance` (`0..1`).
- **`forge:*` (`enabled: false`):** `step_height_addition` (`-512..512`), `nametag_distance` (`0..64`), `entity_gravity` (`-8..8`), `block_reach` (`0..1024`), `entity_reach` (`0..1024`), `swim_speed` (`0..1024`).
- **`skilltree:*` (`enabled: false`):** `evasion` (`0..90`), `blocking` (`0..90`), `stealth` (`0..90`), `exp_per_minute` (`0..100`), `regeneration` (`0..100`).
- **`botania:*` (`enabled: false`):** `pixie_spawn_chance` (`0..1`).

---

## 4. Mandatory Server Invariants

1. **Top-Level Structure:**
   - `attributefix.json` must be valid JSON containing only the single top-level key `"attributes"`.
2. **Attribute Key & Entry Types:**
   - Every key under `"attributes"` must be a non-empty `<namespace>:<path>` string.
   - `"enabled"` must be a strict JSON boolean (`true` or `false`).
   - `"min"` and `"max"` must each contain `"default"` and `"value"` as finite numbers (never strings, `null`, `NaN`, or booleans).
3. **Bound Ordering:**
   - Every attribute must satisfy `min.default <= max.default` and `min.value <= max.value`.
4. **Excluded Runtime State & Artifacts:**
   - Never place secrets, credentials, symlinks, runtime state directories (`logs/`, `world/`, `mods/`), or binary/archive/database artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/attributefix/configs/`.
