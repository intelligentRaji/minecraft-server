---
name: curios-config
description: Inspect and configure Curios common slot definitions and server-side death-retention and menu layout settings in mods/curios/configs/.
---

# Curios Configuration Guide (`curios-config`)

Use this skill to inspect and modify **Curios** (`modpack/server-client/curios-forge-5.14.1+1.20.1.jar`) configuration in `mods/curios/configs/`.

> **Startup / World-Load Forge TOML Configs:** `config/curios-common.toml` and `world/serverconfig/curios-server.toml` are not live-reloadable via RCON; changes require a server restart to take effect. Additionally, changes to `slots` in `config/curios-common.toml` should match client configs to prevent slot/UI desyncs.

---

## 1. Configuration File Overview (`mods/curios/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/curios-common.toml` | Forge common settings: list of Curios slot configuration strings (`slots`) to create or modify slots. | TOML |
| `world/serverconfig/curios-server.toml` | Forge server/world settings: death-retention policy (`keepCurios`) and Curios menu layout (`[menu]`, `[menu.experimental]`). | TOML |

---

## 2. `config/curios-common.toml` Reference

- `slots` (array of strings, default `[]`): List of slot configuration strings used to create new Curios slots or modify existing ones.
  - **Syntax reference:** Follow the official Curios slot configuration syntax documented at `https://docs.illusivesoulworks.com/curios/configuration#slot-configuration`.
  - Keep `slots` as a valid TOML array of quoted strings (e.g. `slots = []`).

---

## 3. `world/serverconfig/curios-server.toml` Reference

### Top-Level Settings
- `keepCurios` (string, default `"DEFAULT"`): Controls whether equipped Curios items are kept or dropped on player death.
  - **Allowed values:**
    - `"ON"` — Curios items are always kept on death.
    - `"DEFAULT"` — Curios items follow the `keepInventory` gamerule.
    - `"OFF"` — Curios items are always dropped on death.

### `[menu]`
- `enableLegacyMenu` (boolean, default `false`): Enables the legacy Curios menu for backwards compatibility.

### `[menu.experimental]`
- `minimumColumns` (integer `1 ~ 8`, default `1`): Minimum number of columns displayed in the Curios menu.
- `maxSlotsPerPage` (integer `1 ~ 48`, default `48`): Maximum number of slots displayed per page of the Curios menu.

---

## 4. Mandatory Invariants

1. **Valid Forge TOML Types, Enums & Ranges:**
   - Keep `slots` as a valid TOML array of strings adhering to Curios slot configuration syntax.
   - Keep `keepCurios` restricted to `"ON"`, `"DEFAULT"`, or `"OFF"`.
   - Keep `enableLegacyMenu` as a boolean (`true` or `false`).
   - Keep `minimumColumns` within `1 ~ 8` and `maxSlotsPerPage` within `1 ~ 48`.
2. **Restart & Client Alignment:**
   - Restart the server after modifying `config/curios-common.toml` or `world/serverconfig/curios-server.toml`.
   - Keep client `curios-common.toml` aligned if `slots` is modified.
3. **Excluded Runtime & World State:**
   - Per-player curio inventories and tags live in `data/world/playerdata/` and are not part of `mods/curios/configs/`.
   - Never place runtime or world state (`data/world/playerdata/`, `data/world/`, `data/logs/`, `data/mods/`) or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/curios/configs/`.
