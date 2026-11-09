---
trigger: always_on
description: Guidelines and constraints for Minecraft mod management, platform priority, and sync
---

# Minecraft Mod Installation & Management Guidelines

## 1. Mod Platform Priority (Modrinth First)
- **Primary Source:** Always search and attempt to install Minecraft mods from **Modrinth** first (via the Modrinth API or Modrinth catalog for Forge 1.20.1).
- **Fallback Protocol (Ask Permission):**
  - If a mod is **NOT** available on Modrinth (e.g. exclusive to CurseForge, GitHub, or author websites), the agent **MUST explicitly ask the user for permission** before downloading or installing the mod from the other platform.
  - The request to the user must state:
    1. Mod name
    2. Missing on Modrinth explanation
    3. Target platform and official source URL
    4. Exact version and loader (e.g. 1.20.1 Forge)

## 2. Strict Category Separation
Every mod `.jar` file must be placed into its appropriate category folder inside `modpack/`:
- **`modpack/server-client/`**: Content mods adding items, blocks, mobs, dimensions, or world generation (e.g. Biomes O' Plenty, Twilight Forest, Farmer's Delight, Dynamic Trees).
- **`modpack/server-only/`**: Headless server utilities, chunk pre-generation, backups, and server performance tools (e.g. Chunky, ModernFix, FerriteCore, Simple Backups).
- **`modpack/client-only/`**: Visual, rendering, HUD, audio, or UI mods (e.g. Embeddium, Distant Horizons, Jade, JEI, Xaero's Minimap). **Never place client-only mods on the server.**

## 3. Automated Synchronization
- After downloading, updating, or deleting `.jar` files in `modpack/`, always run:
  ```bash
  ./sync-mods.sh --restart
  ```
- This ensures both the Docker server (`./data/mods/`) and the Windows Modrinth client (`/mnt/c/Users/sergd/AppData/Roaming/ModrinthApp/profiles/Forge 1.20.1/mods`) remain in sync.

## 4. Verification
- Always check the Docker container startup logs after adding server mods:
  ```bash
  docker compose logs --tail=50 mc
  ```
- Confirm the server reaches: `[Server thread/INFO] [minecraft/DedicatedServer]: Done (...)!`
