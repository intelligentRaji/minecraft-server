---
name: ferritecore-config
description: Inspect and configure FerriteCore server-side memory optimization mixin toggles (blockstate, model, multipart, neighbor lookup, and quad deduplication) in mods/ferritecore/configs/.
---

# FerriteCore Configuration Guide (`ferritecore-config`)

Use this skill to inspect and modify **FerriteCore** (`ferritecore-6.0.1-forge.jar`, server-only memory optimization mod) configuration in `mods/ferritecore/configs/`.

> **Startup-Only Configuration:** FerriteCore mixin options are applied during JVM/Forge mixin bootstrap on server start and are not hot-reloadable. Changes in `mods/ferritecore/configs/config/ferritecore-mixin.toml` require a `mc-forge-server` restart to take effect. Always obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online before restarting.

---

## 1. Configuration File Overview (`mods/ferritecore/configs/`)

| File | Purpose | Format |
| :--- | :--- | :--- |
| `config/ferritecore-mixin.toml` | Mixin feature toggles controlling blockstate, model, neighbor table, and baked quad memory optimizations. | TOML |

---

## 2. `config/ferritecore-mixin.toml` Reference

All 11 options are top-level TOML booleans (`true` or `false`).

| Key | Type | Default | Description & Notes |
| :--- | :--- | :--- | :--- |
| `compactFastMap` | `bool` | `false` | Use a slightly more compact, but also slightly slower representation for block states. |
| `useSmallThreadingDetector` | `bool` | `false` | Replace objects used to detect multi-threaded access to chunks with a much smaller field. Disabled by default due to very rare and hard-to-reproduce crashes; use at your own risk. |
| `cacheMultipartPredicates` | `bool` | `true` | Cache the predicate instances used in multipart models. Required when `multipartDeduplication = true`. |
| `multipartDeduplication` | `bool` | `true` | Do not create a new `MultipartBakedModel` instance for each block state using the same multipart model. **Requires `cacheMultipartPredicates = true`.** |
| `blockstateCacheDeduplication` | `bool` | `true` | Deduplicate cached data for blockstates, most importantly collision and render shapes. |
| `modelResourceLocations` | `bool` | `true` | Avoid creation of new strings when creating `ModelResourceLocation`s. |
| `modelSides` | `bool` | `true` | Use smaller data structures for "simple" models, especially models with few side-specific faces. |
| `replaceNeighborLookup` | `bool` | `true` | Replace the blockstate neighbor table. Required when `replacePropertyMap = true`. |
| `populateNeighborTable` | `bool` | `false` | Populate the neighbor table used by vanilla. Enabling this slightly increases memory usage, but can help with issues in the rare case where mods access it directly. |
| `replacePropertyMap` | `bool` | `true` | Do not store the properties of a state explicitly and read them from the replaced neighbor table instead. **Requires `replaceNeighborLookup = true`.** |
| `bakedQuadDeduplication` | `bool` | `true` | Deduplicate vertex data of baked quads in the basic model implementations. |

---

## 3. Mandatory Server Invariants

1. **Valid TOML & Key Constraints (`config/ferritecore-mixin.toml`):**
   - Every key must hold a valid TOML boolean (`true` or `false`).
   - Only the 11 documented keys above are permitted; no unexpected keys may be added.
2. **Mixin Dependency Invariants:**
   - `multipartDeduplication = true` requires `cacheMultipartPredicates = true`. If disabling `cacheMultipartPredicates`, you must also set `multipartDeduplication = false`.
   - `replacePropertyMap = true` requires `replaceNeighborLookup = true`. If disabling `replaceNeighborLookup`, you must also set `replacePropertyMap = false`.
3. **Excluded Runtime State & Artifacts:**
   - Never place secrets, symlinks, runtime state directories (`logs/`, `world/`, `mods/`), or binary/archive/database artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/ferritecore/configs/`.
