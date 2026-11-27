---
name: chickenchunks-config
description: Inspect and configure Chicken Chunks 1.20.1 static chunkloading policy settings (OP bypass/access, offline chunkloading, logout timeout, and per-player/per-loader chunk limits) in server/mods/chickenchunks/configs/ChickenChunks.cfg using CodeChickenLib .cfg syntax. Use whenever viewing, modifying, or validating ChickenChunks server configuration.
---

# ChickenChunks Configuration Guide (`chickenchunks-config`)

Use this skill to inspect and modify **Chicken Chunks 1.20.1** static server configuration in `server/mods/chickenchunks/configs/ChickenChunks.cfg`.

> **Operational & Reload Notes:**
> - Static edits to `server/mods/chickenchunks/configs/ChickenChunks.cfg` take effect on **`mc-forge-server` startup/restart**. Coordinate with server restart rules before restarting a running server.
> - Per-player chunkloader restrictions (`"playerRestrictions"`) are **not** configured in `ChickenChunks.cfg` here; manage them live in-game using `/chickenchunks restrict player <players> ...`.

---

## 1. Configuration File & Format (`server/mods/chickenchunks/configs/ChickenChunks.cfg`)

- **Exact file path:** `server/mods/chickenchunks/configs/ChickenChunks.cfg`
- **No separate CodeChickenLib config file:** ChickenChunks stores all static settings in `ChickenChunks.cfg`; do not add a separate CodeChickenLib config file or any extra files to `server/mods/chickenchunks/configs/`.
- **CodeChickenLib `.cfg` format rules:**
  - Comments begin with `#`.
  - Entries are top-level typed key/value lines (no TOML `[section]` headers and no JSON):
    - Booleans: `B:"<key>"=<true|false>`
    - Integers: `I:"<key>"=<non-negative integer>`
  - Every key name is double-quoted after its `B:` or `I:` type prefix.

---

## 2. Static Settings Reference (`ChickenChunks.cfg`)

All 6 keys below must remain explicitly declared in `server/mods/chickenchunks/configs/ChickenChunks.cfg` with no duplicate keys and no unexpected keys or `{ ... }` blocks.

| Key | Type Prefix | Valid Values | Server Default | Description |
| :--- | :--- | :--- | :--- | :--- |
| `opsBypassRestrictions` | `B:` | `false` (required) | `false` | Whether players with OP permissions bypass chunk loading restrictions (locked to `false` for server guardrails). |
| `opsAccessAllLoaders` | `B:` | `true` or `false` | `true` | Whether players with OP permissions can manage other users' ChunkLoaders. |
| `allowOffline` | `B:` | `false` (required) | `false` | Whether chunks stay loaded when a ChunkLoader's owner is offline (locked to `false` to protect server TPS/RAM). |
| `offlineTimeout` | `I:` | Integer in `0..60` | `0` | Minutes ChickenChunks waits after a player logs out before unloading their chunks (only effective when `B:"allowOffline"=false`). |
| `totalAllowedChunks` | `I:` | Integer in `1..25` | `25` | Maximum number of chunks each player is allowed to load in total. |
| `chunksPerLoader` | `I:` | Integer in `1..25` (`<= totalAllowedChunks`) | `25` | Maximum number of chunks each ChunkLoader is allowed to load in total. |

### Example `ChickenChunks.cfg`

```cfg
# If Players with OP permissions bypass chunk loading restrictions.
B:"opsBypassRestrictions"=false

# If Players with OP permissions can manage other users ChunkLoaders
B:"opsAccessAllLoaders"=true

# If chunks should stay loaded when a ChunkLoader's owner is offline.
B:"allowOffline"=false

# How long in minutes ChickenChunks should wait after a Player logs out to unload their chunks. Only effective when allowOffline=false
I:"offlineTimeout"=0

# The number of chunks each player is allowed to load in total.
I:"totalAllowedChunks"=25

# The number of chunks each ChunkLoader is allowed to load in total.
I:"chunksPerLoader"=25
```

---

## 3. Live Per-Player Restrictions (`"playerRestrictions"`)

- Do **not** add a `"playerRestrictions" { ... }` block, a `playerRestrictions` key, or its `# Specifies restrictions for each player...` comment block to `server/mods/chickenchunks/configs/ChickenChunks.cfg`.
- Per-player UUID chunkloader overrides are live server runtime state managed in-game (or via RCON) with `/chickenchunks` commands, such as:
  - `/chickenchunks restrict player <players> ...`

---

## 4. Mandatory Invariants & Excluded Files

1. **Exact Schema & Server Policy Bounds:**
   - Keep all 6 static keys present with exact CodeChickenLib `B:` / `I:` prefixes, strict `true`/`false` booleans (`opsBypassRestrictions=false`, `allowOffline=false`), and bounded integers (`offlineTimeout` in `0..60`, `totalAllowedChunks` in `1..25`, `chunksPerLoader` in `1..25` and `<= totalAllowedChunks`).
   - Do not add duplicate keys, extra keys, or `{ ... }` blocks.
2. **Excluded Runtime State & Artifacts:**
   - Never add `chickenchunks/` (such as `world/chickenchunks/` per-dimension chunkloader state), `world/`, `loginTimes.dat`, `data/`, `libs/`, `logs/`, symlinks, or binary/database/runtime/archive files (`*.dat`, `*.jar`, `*.db`, `*.sqlite`, `*.log`, `*.gz`, `*.zip`, `*.tar`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`) to `server/mods/chickenchunks/configs/`.
3. **Zero Secrets:**
   - Never commit credentials, tokens, webhooks, passwords, or private keys in `server/mods/chickenchunks/configs/`.
