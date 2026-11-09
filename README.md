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

### 1. Start the Server
```bash
docker compose up -d
```

### 2. Follow Logs (Server Startup)
```bash
docker compose logs -f mc
```
*(Wait until you see `[Server thread/INFO]: Done (...s)! For help, type "help"`)*

### 3. Stop the Server
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
./sync-mods.sh --dry-run

# Synchronize mods
./sync-mods.sh

# Synchronize mods and automatically restart the server if server mods changed
./sync-mods.sh --restart
```

---

## Connecting from Minecraft (Windows)
- In the Minecraft multiplayer server address, connect to:
  ```text
  localhost:25565
  ```
