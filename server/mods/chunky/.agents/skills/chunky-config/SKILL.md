---
name: chunky-config
description: Inspect and configure Chunky server-side chunk pre-generation settings (schema version, language, restart continuation, chunk force-loading, progress output, and update interval) in mods/chunky/configs/.
---

# Chunky Configuration Guide (`chunky-config`)

Use this skill to inspect and modify **Chunky** (`Chunky-1.3.146.jar`, server-side chunk pre-generation utility) configuration in `mods/chunky/configs/`.

> **Restart & Live Operations:** `mods/chunky/configs/config.json` is startup-loaded, so configuration changes require a server restart (or `/chunky reload` if supported). Pre-generation tasks themselves are managed live via `/chunky ...` commands over RCON/console.

---

## 1. Configuration Files Overview (`mods/chunky/configs/`)

| File | Purpose & Key Settings | Format |
| :--- | :--- | :--- |
| `config.json` | Core Chunky behavior: schema version, localization language, restart task continuation, existing-chunk force-loading, and progress reporting. | JSON |

---

## 2. `config.json` Reference

- `version` (integer `>= 1`, currently `2`): Config schema version used by Chunky. Do not decrement or remove.
- `language` (non-empty string, currently `"en"`): Localization language code for Chunky console and chat messages.
- `continueOnRestart` (boolean, currently `false`): When `true`, saved pre-generation tasks automatically resume when the server restarts. Keep `false` unless unattended multi-restart pre-generation is intended.
- `forceLoadExistingChunks` (boolean, currently `false`): When `true`, forces Chunky to load and re-process already-generated chunks instead of skipping them. Keep `false` for normal pre-generation to avoid unnecessary disk and CPU load.
- `silent` (boolean, currently `false`): Suppresses periodic progress messages in console/chat when `true`.
- `updateInterval` (integer `>= 1`, currently `1`): Interval in seconds between periodic progress updates.

---

## 3. Mandatory Server Invariants

1. **Valid JSON & Field Types (`config.json`):**
   - `version` must be an integer `>= 1`.
   - `language` must be a non-empty string.
   - `continueOnRestart`, `forceLoadExistingChunks`, and `silent` must be JSON booleans (`true` or `false`).
   - `updateInterval` must be an integer `>= 1`.
2. **Excluded Runtime State:**
   - Never place `tasks/` runtime state files (live pre-generation task definitions, progress, coordinates, and timestamps) or non-config artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`) inside `mods/chunky/configs/`.
