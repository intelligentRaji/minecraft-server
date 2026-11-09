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

## Connecting to the Server
- **Local (Host machine):** `localhost:25565`
- **Friends (Playit tunnel):** Use your active playit.gg shareable domain (e.g. `xyz.gl.joinmc.link`).

---

## Server Commands (`CoreCommands`)

Players and server operators have access to the following built-in commands:

### Player Commands
| Command | Description |
| :--- | :--- |
| `/home [name]` / `/sethome [name]` | Teleport to or set a named home |
| `/delhome <name>` / `/homes` | Delete a home or view clickable list of homes |
| `/warp [name]` / `/warps` | Teleport to a server warp or list all warps |
| `/spawn` | Teleport to world spawn |
| `/back` | Teleport back to your last location or death point |
| `/rtp` | Randomly teleport to a safe location in the wild |
| `/tpa <player>` / `/tpahere <player>` | Send teleport request to a player |
| `/tpaccept` / `/tpdeny` / `/tpcancel` | Accept, deny, or cancel a teleport request |
| `/msg <player>` / `/reply` | Send private whispers |
| `/ping` / `/afk` / `/playtime` | Check latency, toggle AFK, or view total playtime |

### Operator & Moderation Commands (OP Only)
| Command | Description |
| :--- | :--- |
| `/setwarp <name>` / `/delwarp <name>` | Create or remove a public server warp |
| `/setspawn` | Set world spawn to current location |
| `/tempban <player> <time> [reason]` | Temporarily ban a player (e.g. `/tempban Steve 1d`) |
| `/unban <player>` / `/checkban <player>` | Unban player or check active ban details |
| `/mute <player>` / `/unmute <player>` | Mute or unmute a player in chat |
| `/freeze <player>` | Freeze a player in place |
| `/invsee <player>` | Inspect a player's inventory, armor, and off-hand |
| `/fly` / `/god` / `/heal` / `/feed` | Toggle flight, invulnerability, or restore health/hunger |
| `/region wand` / `/region create <name>` | Define and manage protected areas and flags |
