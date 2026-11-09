# Minecraft Forge 1.20.1 Server (Docker)

This repository contains the Docker Compose setup for a modded Minecraft server using the [`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server) image.

## Server Specifications
- **Edition:** Java Edition
- **Version:** 1.20.1
- **Mod Loader:** Forge
- **Allocated RAM:** 6 GB
- **Port:** 25565

---

## Quick Start

You can manage the server using `make` commands or direct `docker compose` commands.

### Using Make Shortcuts

| Command | Description |
| :--- | :--- |
| `make up` | Start server in background |
| `make down` | Stop server |
| `make restart` | Restart server container |
| `make logs` | Follow server logs in real-time |
| `make status` | View container status |
| `make sync` | Sync mods to Docker + Modrinth client (restarts server if changed) |
| `make sync-dry` | Preview mod synchronization without touching files |
| `make backup` | Upload current modpack to Google Drive |
| `make progress` | Display Chunky pre-generation progress (alias for `make chunky-progress`) |
| `make chunky-start` | Start Chunky pre-generation task |
| `make chunky-pause` | Pause Chunky pre-generation task and save progress |
| `make chunky-continue` | Continue paused Chunky pre-generation task |
| `make chunky-cancel` | Cancel and delete current Chunky task |
| `make chunky-selection` | Display current Chunky shape and radius selection |

---

### Manual Docker Compose

#### 1. Start the Server
```bash
docker compose up -d
```

#### 2. Follow Logs (Server Startup)
```bash
docker compose logs -f mc
```
*(Wait until you see `[Server thread/INFO]: Done (...s)! For help, type "help"`)*

#### 3. Stop the Server
```bash
docker compose down
```

---

## Managing Mods

Mods are organized in the `modpack/` folder by target:

```text
minecraft-server/
├── modpack/
│   ├── server-client/ # Content mods required on BOTH server and client (e.g. Biomes O' Plenty, Twilight Forest)
│   ├── server-only/   # Server-side mods (e.g. Spark, Chunky, admin tools)
│   └── client-only/   # Client-side mods (e.g. Embeddium, Distant Horizons, Jade, JEI, Xaero's)
```

### Synchronize Mods

Run the sync script to automatically distribute mods to the Docker server (`./data/mods/`) and your Windows Modrinth profile (`Forge 1.20.1`):

```bash
# Preview what will be synced
python3 .agents/skills/minecraft-mod-manager/scripts/sync_mods.py --dry-run

# Synchronize mods
python3 .agents/skills/minecraft-mod-manager/scripts/sync_mods.py

# Synchronize mods and automatically restart the server if server mods changed
python3 .agents/skills/minecraft-mod-manager/scripts/sync_mods.py --restart
```

---

## Connecting from Minecraft (Windows)
- In the Minecraft multiplayer server address, connect to:
  ```text
  localhost:25565
  ```
