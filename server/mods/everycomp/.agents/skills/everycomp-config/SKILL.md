---
name: everycomp-config
description: Inspect and configure Every Compat (Wood Good) settings (dynamic assets, creative tabs, tooltips, safe recipe/tab entry toggles, and conditional registration blacklists) in mods/everycomp/configs/.
---

# Every Compat (Wood Good) Configuration Guide (`everycomp-config`)

Use this skill to inspect and modify **Every Compat (Wood Good)** configuration in `mods/everycomp/configs/`.

> **Startup Forge TOML Configs:** `config/everycomp-common.toml`, `config/everycomp-entries.toml`, and `config/everycomp-hazardous.toml` are loaded at startup and are not live-reloadable via RCON; changes require a server restart to take effect.

---

## 1. Configuration File Overview (`mods/everycomp/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/everycomp-common.toml` | General settings (dynamic asset generation, creative tabs, blocktype tags, debug/version-check packets) and tooltip toggles. | TOML |
| `config/everycomp-entries.toml` | Safe boolean toggles that hide specific wood/leaf types or entry sets from creative tabs and disable their recipes without altering block/item registration. | TOML |
| `config/everycomp-hazardous.toml` | Conditional registration blacklists (`woodtype`, `leavestype`, `block`, `entryset`, `module`) and `include_all_wood_modules`. **Requires exact client-server parity.** | TOML |

---

## 2. `config/everycomp-common.toml` Reference

### `[general]`
- `generate_dynamic_assets` (boolean, default `true`): Enables dynamic asset generation. Required for Every Compat to work properly unless all generated assets are supplied manually via datapack.
- `creative_tab` (boolean, default `true`): Places added items into a dedicated Every Compat creative tab instead of only their parent mod tabs.
- `tab_item_search` (boolean, default `true`): Enables the search bar in the Every Compat creative tab.
- `no_mod_creative_tab` (boolean, default `false`): When `true`, prevents generated items from being placed into their parent mod's creative tab.
- `generate_blocktype_tags` (boolean, default `false`): Generates blocktype tags for every block type across all mods using the system. Keep `false` for faster startup unless needed.
- `save_debug_resources` (boolean, default `false`): Saves dynamically generated resources into a debug folder inside the instance directory. Keep `false` in production.
- `mod_version_check_packet` (boolean, default `true`): Sends a packet on connect to verify dependency mod versions match between client and server.
- `debug_packet` (boolean, default `false`): Debug packet toggle. Keep `false` unless troubleshooting.

### `[general.tooltips]`
- `mod_origin_enabled` (boolean, default `true`): Shows tooltips indicating which mod an Every Compat item comes from.
- `block_type_enabled` (boolean, default `true`): Shows tooltips indicating which block type an Every Compat item is made from.
- `show_on_advanced_tooltips` (boolean, default `false`): When `true`, restricts Every Compat tooltips to advanced tooltips (`F3+H`).

---

## 3. `config/everycomp-entries.toml` Reference

> **Safe Server-Side Toggles:** Changing booleans in `everycomp-entries.toml` only hides items from creative tabs and disables their recipes; blocks and items remain registered, so server-side changes do not break client-server registry parity.

All leaf keys are booleans (`true` = enabled, `false` = hidden from tabs and recipe disabled).

### `[types.wood_type.<modid>]`
- `biomesoplenty` (13 types): `fir`, `pine`, `maple`, `redwood`, `mahogany`, `jacaranda`, `palm`, `willow`, `dead`, `magic`, `umbran`, `hellbark`, `empyreal`
- `twilightforest` (8 types): `twilight_oak`, `canopy`, `mangrove`, `dark`, `time`, `transformation`, `mining`, `sorting`
- `minecraft` (2 types): `pale_oak`, `poplar`
- `botania` (2 types): `livingwood`, `dreamwood`

### `[types.leaves_type.<modid>]`
- `biomesoplenty` (21 types): `null`, `origin`, `flowering_oak`, `cypress`, `snowblossom`, `rainbow_birch`, `fir`, `pine`, `red_maple`, `orange_maple`, `yellow_maple`, `redwood`, `mahogany`, `jacaranda`, `palm`, `willow`, `dead`, `magic`, `umbran`, `hellbark`, `empyreal`
- `twilightforest` (11 types): `thorn`, `beanstalk`, `twilight_oak`, `canopy`, `mangrove`, `dark`, `rainbow_oak`, `time`, `transformation`, `mining`, `sorting`
- `minecraft` (4 types): `pale_oak`, `red_poplar`, `orange_poplar`, `yellow_poplar`

### `[entries.wood_type.<modid>]`
- `handcrafted` (15 entries): `counter`, `corner_trim`, `fancy_bed`, `desk`, `couch`, `shelf`, `nightstand`, `table`, `chair`, `drawer`, `cupboard`, `pillar_trim`, `dining_bench`, `side_table`, `bench`
- `twilightforest` (4 entries): `hollow_log_horizontal`, `hollow_log_vertical`, `banister`, `hollow_log_climbable`
- `farmersdelight` (1 entry): `cabinet`
- `vanillabackport` (1 entry): `shelf`
- `create` (2 entries): `window`, `window_pane`

---

## 4. `config/everycomp-hazardous.toml` Reference

> **CRITICAL CLIENT-SERVER PARITY:** `everycomp-hazardous.toml` controls conditional block and item registration. Changing any blacklist or `include_all_wood_modules` on the server without applying the exact same change on all clients will prevent players from joining due to registry mismatch.

All `blacklist` keys accept a list of valid, non-empty regex strings (default `[]`).

### `[woodtype]`
- `blacklist` (array of strings, default `[]`): Excludes matching wood types across all modules using `"modid:woodtype"` regexes (e.g., `"biomesoplenty:redwood"`, `"biomesoplenty:.*"`).

### `[leavestype]`
- `blacklist` (array of strings, default `[]`): Excludes matching leaf types across all modules using `"modid:leavestype"` regexes.

### `[block]`
- `blacklist` (array of strings, default `[]`): Excludes specific Wood-Good blocks using `"supported_mod/wood_mod/block_id"` regexes (e.g., `"chipped/biomesoplenty/checkered_redwood_trapdoor"`, `".*/biomesoplenty/fir_chest"`).

### `[entryset]`
- `blacklist` (array of strings, default `[]`): Excludes an entire entry set from a supported Wood-Good module across all wood/leaf types using `"supported_mod:entry_name"` regexes (e.g., `"chipped:checkered_trapdoor"`, `"chipped:.*"`).

### `[module]`
- `blacklist` (array of strings, default `[]`): List of supported mod IDs to exclude across Wood-Good, Stone-Zone, and Gems-Realm (e.g., `"chipped"`).

### `[other]`
- `include_all_wood_modules` (boolean, default `true`): When `false`, disables all supported wood modules on Every Compat's side. Must match between client and server.

---

## 5. Mandatory Invariants

1. **Client-Server Registry Parity (`everycomp-hazardous.toml`):**
   - Never modify `[woodtype].blacklist`, `[leavestype].blacklist`, `[block].blacklist`, `[entryset].blacklist`, `[module].blacklist`, or `[other].include_all_wood_modules` on the server unless all clients receive the identical configuration.
   - Ensure every blacklist entry is a valid, non-empty regex string.
2. **Production Defaults (`everycomp-common.toml`):**
   - Keep `generate_dynamic_assets = true` (unless supplying all assets manually via datapack).
   - Keep `save_debug_resources = false` and `debug_packet = false` in production.
3. **Restart Discipline:**
   - All `everycomp-*.toml` files are loaded at startup and are not live-reloadable via RCON; restart the server after changes.
4. **Excluded Files & Runtime State:**
   - Do not include generated debug resource dumps, `logs/`, `world/`, `mods/`, or any credential/secret files in `mods/everycomp/configs/`.
   - Never place binary or runtime artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/everycomp/configs/`.
