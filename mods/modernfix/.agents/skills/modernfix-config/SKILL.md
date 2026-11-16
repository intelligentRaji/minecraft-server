---
name: modernfix-config
description: Inspect and configure ModernFix performance, bugfix, and memory-optimization settings (async JEI plugin blacklist, mixin toggles, and stability level) in mods/modernfix/configs/.
---

# ModernFix Configuration Guide (`modernfix-config`)

Use this skill to inspect and modify **ModernFix** (`modernfix-forge-5.27.91+mc1.20.1.jar`, performance, bugfix, and memory-optimization mod) configuration in `mods/modernfix/configs/`.

> **Startup-Only Configuration:** ModernFix mixins and common settings are applied at JVM/Forge launch, so changes in `mods/modernfix/configs/` require a `mc-forge-server` restart to take effect. Always obtain explicit user confirmation and run `list` and `save-all` via RCON if players may be online before restarting.

---

## 1. Configuration Files Overview (`mods/modernfix/configs/`)

| File | Purpose & Key Settings | Format |
| :--- | :--- | :--- |
| `modernfix-common.toml` | Common runtime settings, including `blacklist_async_jei_plugins` for JEI plugins that must load on the main thread. | TOML |
| `modernfix-mixins.properties` | Mixin feature/bugfix/performance toggles and `stability_level` override flags. | Java `.properties` |

---

## 2. `modernfix-common.toml` Reference

- `blacklist_async_jei_plugins` (array of non-empty strings, currently `["jepb:jei_plugin"]`): List of JEI plugin IDs that are forced to load synchronously on the main thread instead of asynchronously, preventing thread-safety crashes in incompatible plugins.
- Do not add unexpected keys to `modernfix-common.toml`.

---

## 3. `modernfix-mixins.properties` Reference

The file lists all available mixin options as commented-out defaults (`#  <key>=<value> # (default)`). Do not uncomment or edit the default reference lines; instead, append overrides as uncommented `key=value` lines below `# User overrides go here.` at the bottom of the file.

### Override Syntax
- **Mixin toggles (`mixin.*`):** `mixin.<category>.<name>=true|false` (or top-level `mixin.devenv=true|false`, `mixin.safety=true|false`).
  - `mixin.bugfix.*`: Bugfix and leak-prevention mixins (e.g., `chunk_deadlock`, `concurrency`, `world_leaks`, `paper_chunk_patches`).
  - `mixin.feature.*`: Optional behavioral/diagnostic features (e.g., `branding`, `remove_telemetry`, `spark_profile_launch`, `integrated_server_watchdog`).
  - `mixin.launch.*`: Startup/classloading optimizations (e.g., `class_search_cache`).
  - `mixin.perf.*`: Memory and CPU performance optimizations (e.g., `dynamic_resources`, `compact_bit_storage`, `faster_capabilities`, `worldgen_allocation`).
  - `mixin.devenv`: Development-environment mixin toggle (default `false`).
  - `mixin.safety`: Safety checks for mixin compatibility (default `true`).
- **Stability level (`stability_level`):** `stability_level=GA|BETA|ALPHA` (default `GA`). Controls whether experimental (`BETA`/`ALPHA`) mixins are eligible to load.

---

## 4. Mandatory Server Invariants

1. **Valid TOML & Key Constraints (`modernfix-common.toml`):**
   - `blacklist_async_jei_plugins` must be a valid TOML array of non-empty strings.
   - No unexpected keys may be present.
2. **Valid `.properties` Overrides (`modernfix-mixins.properties`):**
   - Only valid `mixin.*=true|false` and `stability_level=GA|BETA|ALPHA` keys are allowed.
   - No unexpected keys may be present.
3. **Excluded Runtime State & Artifacts:**
   - Never place secrets, symlinks, runtime state directories (`logs/`, `world/`, `mods/`), or binary/archive/database artifacts (`*.jar`, `*.db`, `*.log`, `*.tmp`, `*.lock`, `*.zip`, `*.tar.gz`) inside `mods/modernfix/configs/`.
