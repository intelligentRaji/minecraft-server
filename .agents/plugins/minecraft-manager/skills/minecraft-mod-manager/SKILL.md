---
name: minecraft-mod-manager
description: >-
  Step-by-step instructions for installing, synchronizing, and verifying
  Minecraft Forge 1.20.1 mods across Docker server and Windows Modrinth App client.
---

# Minecraft Mod Installation Runbook

Step-by-step procedure for installing and configuring mods.

---

### Step 1: Discover & Inspect Mod Compatibility
Query the mod on Modrinth for Forge 1.20.1 compatibility and inspect any required dependencies *(requires network access — use `BypassSandbox: true`)*:
```bash
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-manager/scripts/query_modrinth.py <slug>
```
*(For raw API specifications, see [references/modrinth_api.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/skills/minecraft-mod-manager/references/modrinth_api.md)).*

---

### Step 2: Download Mod into Target Category
Download or place the `.jar` file directly into the appropriate folder inside `modpack/`:
* Content mods (blocks, mobs, worldgen) $\rightarrow$ `modpack/server-client/`
* Headless server utilities (backups, optimization) $\rightarrow$ `modpack/server-only/`
* UI / HUD / Rendering $\rightarrow$ `modpack/client-only/`

```bash
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-manager/scripts/query_modrinth.py <slug> --download-to modpack/<category>
```
Repeat for any required dependencies reported in Step 1.

---

### Step 3: Apply Changes & Verify Server Health
* **For `server-client` or `server-only` mod changes:** Ask the user to run `make restart` (`make sync-dry` previews changes). Once restarted, verify logs report ready:

```bash
docker compose logs --tail=50 mc
```
Confirm the server reports:
```text
[Server thread/INFO] [minecraft/DedicatedServer]: Done (...s)! For help, type "help"
```
If the newly installed mods generated new configuration files in `server/data/config/` or `server/data/world/serverconfig/`, activate **`minecraft-mod-harness-manager`** in Step 4 to create their `server/mods/<slug>/` vertical slices.
* **For `client-only` mod changes (no `mc` restart needed):** Run `make reload` so `modsync-api` refreshes `/api/manifest` (no WebSocket push is sent; players receive them when clicking **Install Recommended Client Mods**).

---

### Step 4: Create or Remove Mod Config Harness
After adding or removing a server mod (`server-client` or `server-only`) in `modpack/`:

1. **After Installing a Server Mod:**
   Activate **`minecraft-mod-harness-manager`** to onboard `server/mods/<slug>/`.
2. **After Removing a Server Mod:**
   Activate **`minecraft-mod-harness-manager`** (`remove_mod_harness.py <slug>`) to delete `server/mods/<slug>/`.

---

### Step 5: Synchronize with Google Drive (Final Step)
After any mod additions, upgrades, or deletions are verified locally:
1. **Adding / Updating Mods:** Ask the user:
   > *"Would you like me to upload the updated mods to your Google Drive (`minecraft-server/mods/`) for safe backup and sharing?"*
2. **Removing Mods:** Ask the user:
   > *"Would you like me to remove the deleted mods from your Google Drive (`minecraft-server/mods/`) to maintain zero drift?"*

Upon user approval, activate the **`minecraft-gdrive-sync`** skill to perform the Google Drive synchronization.

---

### Step 6: Troubleshooting Startup Errors
1. **Missing Dependency Range:** Check logs for `Missing or unsupported mandatory dependencies: Mod ID: '<id>'`. Query and download the missing library using Steps 1–3.
2. **Headless Crash:** If a `NoClassDefFoundError` or rendering error appears, ensure no client-side UI mods were placed into `server-client/` or `server-only/`. Move them to `client-only/`, then ask the user to run `make restart` to prune them from `server/data/mods/`.
