---
name: skilltree-config
description: Inspect and configure Passive Skill Tree settings (skill points, levelup costs, gem drops, equipment sockets, amnesia scrolls, grindstone XP, and mixtures) in mods/skilltree/configs/.
---

# Passive Skill Tree Configuration Guide (`skilltree-config`)

Use this skill to inspect and modify **Passive Skill Tree** (`modpack/server-client/PassiveSkillTree-1.20.1-BETA-0.6.14a-all.jar`) configuration in `mods/skilltree/configs/`.

> **Startup-Only Forge TOML Configs:** Changes to `skilltree-common.toml` and `skilltree-server.toml` take effect on server start/restart. Note that `skilltree-server.toml` overrides server-side `["Skill Points"]`, `["Amnesia Scroll"]`, and `[Experience]` settings for the world.

---

## 1. Configuration Files Overview (`mods/skilltree/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `skilltree-common.toml` | Shared Forge common settings: skill point caps and costs, gem drop chance, default equipment socket counts & item blacklist, amnesia scroll penalty/drop, grindstone XP multiplier, and mixture multipliers. | TOML |
| `skilltree-server.toml` | World/server-side overrides for `["Skill Points"]`, `["Amnesia Scroll"]`, and `[Experience]`. | TOML |

---

## 2. `skilltree-common.toml` Reference

### `["Skill Points"]`
- `"Maximum skill points"` (integer `1 ~ 1000`, default `85`): Maximum number of skill points a player can obtain.
- `"First skill point cost"` (integer `> 0`, default `15`): Experience cost for the first skill point.
- `"Last skill point cost"` (integer `> 0`, default `1400`): Experience cost for the final skill point when using the automatic cost curve.
- `"Use skill points costs array"` (boolean, default `false`): When `true`, uses the explicit `"Levelup costs"` array instead of interpolating between first and last costs.
- `"Levelup costs"` (array of integers `> 0`, default 85 entries): Per-point cost list. **Array length MUST equal `"Maximum skill points"`.**
- `"Show chat messages"` (boolean, default `true`): Shows a chat message when a player gains a skill point.
- `"Enable exprerience exchange for skill points"` (boolean, default `true`): Enables exchanging experience for skill points. **Note exact key spelling: `exprerience`.** If disabled, ensure an alternative way to earn skill points exists.

### `[Gems]`
- `"Base drop chance"` (float `0.0 ~ 1.0`, default `0.15`): Base probability for gem drops.

### `[Equipment]`
- `"Default Helmets Sockets"` (integer `0 ~ 4`, default `1`)
- `"Default Chestplates Sockets"` (integer `0 ~ 4`, default `1`)
- `"Default Leggings Sockets"` (integer `0 ~ 4`, default `0`)
- `"Default Boots Sockets"` (integer `0 ~ 4`, default `1`)
- `"Default Weapons Sockets"` (integer `0 ~ 4`, default `1`)
- `"Default Shields Sockets"` (integer `0 ~ 4`, default `1`)
- `"Default Rings Sockets"` (integer `0 ~ 4`, default `1`)
- `"Default Necklaces Sockets"` (integer `0 ~ 4`, default `1`)
- `"IDs of items that shouldn't have sockets"` (array of strings, default `[]`): Blacklist specific items, whole mods, or all items from receiving sockets:
  - Specific items: `["minecraft:diamond_hoe", "minecraft:golden_hoe"]`
  - Whole mod: `["<mod_id>:*"]`
  - All items: `["*:*"]`

### `["Amnesia Scroll"]`
- `"Amnesia scroll penalty"` (float `0.0 ~ 1.0`, default `0.2`): Percentage of levels a player loses when using an amnesia scroll.
- `"Drop amnesia scrolls from the Ender Dragon"` (boolean, default `true`): Whether the Ender Dragon drops amnesia scrolls.

### `[Experience]`
- `"Grindstone experience multiplier"` (float `0.0 ~ 1.0`, default `0.1`): Multiplier applied to experience gained from grindstones.

### `[Mixtures]`
- `"Effects duration multiplier"` (float `0.0 ~ 2.0`, default `1.0`): Multiplier for mixture effect durations.
- `"Effects strength multiplier"` (float `0.0 ~ 2.0`, default `1.0`): Multiplier for mixture effect strengths.

---

## 3. `skilltree-server.toml` Reference (World / Server Overrides)

`skilltree-server.toml` overrides the server-side skill point, amnesia scroll, and grindstone experience settings for the world:

### `["Skill Points"]`
- `"Maximum skill points"` (integer `> 1`, default `100`): Server-side maximum skill points cap.
- `"First skill point cost"` (integer `> 0`, default `15`): Experience cost for the first skill point.
- `"Last skill point cost"` (integer `> 0`, default `1400`): Experience cost for the last skill point.
- `"Use skill points costs array"` (boolean, default `false`): When `true`, uses `"Levelup costs"` instead of the interpolated curve.
- `"Levelup costs"` (array of integers `> 0`, default 100 entries): Per-point cost list. **Array length MUST equal `"Maximum skill points"`.**
- `"Show chat messages"` (boolean, default `true`): Shows chat notifications on skill point gain.
- `"Enable exprerience exchange for skill points"` (boolean, default `true`): Enables exchanging experience for skill points (note exact key spelling `exprerience`).

### `["Amnesia Scroll"]`
- `"Amnesia scroll penalty"` (float `0.0 ~ 1.0`, default `0.2`): Percentage of levels lost when using an amnesia scroll.
- `"Drop amnesia scrolls from the Ender Dragon"` (boolean, default `true`): Whether the Ender Dragon drops amnesia scrolls.

### `[Experience]`
- `"Grindstone experience multiplier"` (float `0.0 ~ 1.0`, default `0.1`): Multiplier for grindstone experience.

---

## 4. Mandatory Invariants

1. **Exact Key Names & TOML Validity:**
   - Keep quoted keys exact, including `"Enable exprerience exchange for skill points"`.
   - Ensure all values remain valid TOML types and within documented Forge ranges.
2. **Matching `"Levelup costs"` Length:**
   - Whenever `"Maximum skill points"` is changed in `skilltree-common.toml` or `skilltree-server.toml`, update `"Levelup costs"` in that same file so its array length equals `"Maximum skill points"` and all entries are `> 0`.
3. **Common vs. Server Alignment:**
   - Because `skilltree-server.toml` overrides server-side `["Skill Points"]`, `["Amnesia Scroll"]`, and `[Experience]` settings, keep shared keys aligned across both files when adjusting progression or XP values.
4. **Excluded Runtime & Player State:**
   - Never place runtime or player state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/skilltree/configs/`.
