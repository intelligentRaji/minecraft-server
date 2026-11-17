---
name: jeresources-config
description: Inspect and configure Just Enough Resources (JER) settings (JEI layout grid, DIY data, dev tooltips, enchantment/dimension blacklists, hidden tabs, and loot manager reloading) in mods/jeresources/configs/.
---

# Just Enough Resources Configuration Guide (`jeresources-config`)

Use this skill to inspect and modify **Just Enough Resources** (`jeresources`, server-client JEI resource/loot/world-gen integration mod) configuration in `mods/jeresources/configs/`.

> **Startup-Only Configuration:** Just Enough Resources settings are loaded during Forge startup and JEI plugin initialization and are not hot-reloadable. Changes in `mods/jeresources/configs/` require a `mc-forge-server` restart to take effect. Always obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online before restarting.

---

## 1. Configuration File Overview (`mods/jeresources/configs/`)

| File | Purpose | Format |
| :--- | :--- | :--- |
| `config/jeresources-common.toml` | Common/server JER configuration for JEI grid layout, resource data toggles, blacklists, hidden tabs, and loot reloading. | TOML |
| `config/jeresources.toml` | Legacy/root JER configuration mirroring the same 8 top-level keys. | TOML |

---

## 2. Configuration Key Reference (`jeresources-common.toml` & `jeresources.toml`)

Both files share the exact same 8 top-level TOML keys:

| Key | Type & Range | Current Value | Description & Notes |
| :--- | :--- | :--- | :--- |
| `itemsPerColumn` | `int` (`1..4`) | `4` | Number of items displayed per column in JER JEI recipe views. |
| `itemsPerRow` | `int` (`1..4`) | `4` | Number of items displayed per row in JER JEI recipe views. |
| `diyData` | `bool` | `true` | Enables built-in/DIY JER resource data. |
| `showDevData` | `bool` | `false` | Displays developer/debug information in JER tooltips and views. |
| `enchantsBlacklist` | `list[str]` | `["flimflam", "soulBound"]` | Enchantment identifiers excluded from JER enchantability and loot displays. |
| `hiddenTabs` | `list[str]` | `[]` | JER JEI tab identifiers to hide from the JEI interface. |
| `dimensionsBlacklist` | `list[int]` | `[-11]` | Dimension IDs excluded from JER world-gen and ore distribution tabs. |
| `disableLootManagerReloading` | `bool` | `false` | Disables JER's loot manager reloading hook. |

---

## 3. Mandatory Server Invariants

1. **Valid TOML & Type Constraints:**
   - Both `config/jeresources-common.toml` and `config/jeresources.toml` must remain valid TOML containing only the 8 documented keys above.
   - `itemsPerColumn` and `itemsPerRow` must be integers within `1..4` (inclusive).
   - `diyData`, `showDevData`, and `disableLootManagerReloading` must be TOML booleans (`true` or `false`).
   - `enchantsBlacklist` and `hiddenTabs` must be TOML string arrays (`list[str]`).
   - `dimensionsBlacklist` must be a TOML integer array (`list[int]`).
2. **Cross-File Consistency:**
   - Update both `config/jeresources-common.toml` and `config/jeresources.toml` together when changing shared settings unless an intentional divergence is required.
3. **Excluded Runtime State & Artifacts:**
   - Never place secrets, symlinks, runtime state directories (`logs/`, `world/`, `mods/`), or binary/archive/database artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/jeresources/configs/`.
