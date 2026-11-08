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

## Adding Mods

1. Mod `.jar` files go into the `./data/mods/` directory.
2. From Windows File Explorer, you can open:
   ```text
   \\wsl$\Ubuntu-24.04\home\wakaria\dev\minecraft-server\data\mods
   ```
3. After dropping mods, restart the container:
   ```bash
   docker compose restart mc
   ```

---

## Connecting from Minecraft (Windows)
- In the Minecraft multiplayer server address, connect to:
  ```text
  localhost:25565
  ```
