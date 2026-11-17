# Minecraft Forge 1.20.1 Server & ModSync Monorepo

This monorepo contains:
- **`docker-compose.yml` & `.env`** — Root Docker Compose stack for the Forge 1.20.1 Minecraft server ([`itzg/minecraft-server`](https://github.com/itzg/docker-minecraft-server)), `modsync-api`, and the WireGuard tunnel (`wireguard/`).
- **`server/`** — Minecraft server runtime (`server/data/`), per-mod configuration bridges (`server/mods/`), and modpack jars (`server/modpack/`).
- **`modsync_api/`** — FastAPI WebSocket + HTTP distribution service (`modsync-api`).
- **`client/`** — Standalone Python background synchronizer & system tray app (`modsync-client`) that players install to automatically stay in sync with the server over WebSocket (`wss://`) + HTTPS.

## Server Specifications
- **Edition:** Java Edition
- **Version:** 1.20.1
- **Mod Loader:** Forge
- **Allocated RAM:** 6 GB
- **Ports:** `25565` (Minecraft), `80`/`443` (Caddy HTTPS/WSS reverse proxy for ModSync)

---

## Quick Start

You can manage the server using `make` commands or direct `docker compose` commands.

### Using Make Shortcuts

| Command | Description |
| :--- | :--- |
| `make up` | Start Minecraft server + `modsync-api` + WireGuard |
| `make down` | Stop server stack |
| `make restart` | Restart Minecraft server container |
| `make logs` | Follow Minecraft server logs in real-time |
| `make modsync-logs` | Follow `modsync-api` WebSocket/HTTP logs |
| `make status` | View container status |
| `make sync` | Sync `server/modpack/` to `server/data/mods/`, restart `mc` if changed, and broadcast WebSocket update |
| `make sync-dry` | Preview server mod synchronization without touching files |
| `make backup` | Upload current modpack to Google Drive |
| `make test` | Run unit tests across server config runner, `modsync_api`, and `client` |
| `make client-build` | Build standalone client executable via PyInstaller |
| `make progress` | Display Chunky pre-generation progress (alias for `make chunky-progress`) |
| `make chunky-start` | Start Chunky pre-generation task |
| `make chunky-pause` | Pause Chunky pre-generation task and save progress |
| `make chunky-continue` | Continue paused Chunky pre-generation task |
| `make chunky-cancel` | Cancel and delete current Chunky task |
| `make chunky-selection` | Display current Chunky shape and radius selection |

---

### VPS Reverse Proxy (Caddy over WireGuard)

Caddy runs directly on the VPS (`/opt/modsync-caddy/`) and proxies `/api/*`, `/ws`, and `/health` over the WireGuard tunnel to `10.100.0.2:8080`.
* Without a domain: Caddy listens on `:80` and players connect to `http://<VPS_IP>`.
* With a domain: replace `:80` in the VPS `Caddyfile` with `mods.yourdomain.com` so Caddy automatically provisions Let's Encrypt HTTPS/WSS on port `443`.

### Client Release (`client-v*`)

Push a tag matching `client-v*` (e.g., `git tag client-v0.1.0 && git push origin client-v0.1.0`) to trigger [release-client.yml](file:///home/wakaria/dev/minecraft-server/.github/workflows/release-client.yml), which builds `ModSync.exe` (Windows) and `ModSync-linux` (Linux) and publishes a GitHub Release.

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

Mods are organized in `server/modpack/` by target:

```text
minecraft-server/
├── docker-compose.yml     # Root Compose stack (mc, modsync-api, wireguard)
├── .env                   # Secrets & environment overrides (from .env.example)
├── modsync_api/           # FastAPI WebSocket + HTTP manifest & jar server
├── client/                # Standalone Python tray/daemon client for players
├── wireguard/             # WireGuard tunnel configuration (gitignored)
└── server/
    ├── data/              # Minecraft server runtime & worlds (gitignored)
    ├── mods/              # Per-mod configuration bridges & sync script
    └── modpack/
        ├── server-client/ # Content mods required on BOTH server and client (e.g. Biomes O' Plenty, Twilight Forest)
        ├── server-only/   # Server-side mods (e.g. Spark, Chunky, admin tools)
        └── client-only/   # Client-side mods (e.g. Embeddium, Distant Horizons, Jade, JEI, Xaero's)
```

### Synchronize Mods

Run the sync script to distribute server mods to `server/data/mods/` and notify `modsync-api` so connected players update immediately:

```bash
# Preview what will be synced
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-manager/scripts/sync_mods.py --dry-run

# Synchronize server mods, restart mc if changed, and push WebSocket update
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-manager/scripts/sync_mods.py --restart
```

### Installed Mods

#### `modpack/server-client/` (Server & Client)
| Mod | Jar |
| :--- | :--- |
| AttributeFix | `AttributeFix-Forge-1.20.1-21.0.5.jar` |
| Biomes O' Plenty | `BiomesOPlenty-forge-1.20.1-19.0.0.96.jar` |
| Botania | `Botania-1.20.1-456-FORGE.jar` |
| CoreCommands | `corecommands-2.0.1.jar` |
| Create | `create-1.20.1-6.0.8.jar` |
| Create: Slice & Dice | `sliceanddice-forge-3.6.0.jar` |
| Curios API | `curios-forge-5.14.1+1.20.1.jar` |
| Dynamic Trees | `DynamicTrees-1.20.1-1.4.11.jar` |
| Dynamic Trees - Biomes O' Plenty | `DynamicTreesBOP-1.20.1-3.3.4.jar` |
| Every Compat (Wood Good) | `everycomp-1.20-2.9.29-forge.jar` |
| Farmer's Cutting: Biomes O' Plenty | `farmers-cutting-biomes-o-plenty-1.0.0.jar` |
| Farmer's Delight | `FarmersDelight-1.20.1-1.3.4.jar` |
| FCM Clans | `fcmclans-0.1.0.jar` |
| GlitchCore | `GlitchCore-forge-1.20.1-0.0.1.1.jar` |
| Handcrafted | `handcrafted-forge-1.20.1-3.0.6.jar` |
| ItemProductionLib | `ItemProductionLib-1.20.1-1.0.2b-all.jar` |
| Jade | `Jade-1.20.1-Forge-11.13.3.jar` |
| Just Enough Items (JEI) | `jei-1.20.1-forge-15.74.0.234.jar` |
| Just Enough Resources (JER) | `JustEnoughResources-1.20.1-1.4.0.247.jar` |
| Kotlin for Forge *(Create: Slice & Dice dep)* | `kotlinforforge-4.12.0-all.jar` |
| Moonlight Lib | `moonlight-1.20-2.16.39-forge.jar` |
| Passive Skill Tree | `PassiveSkillTree-1.20.1-BETA-0.6.14a-all.jar` |
| Patchouli *(Botania dep)* | `Patchouli-1.20.1-85-FORGE.jar` |
| Platform *(Vanilla Backport dep)* | `Platform-forge-1.20.1-1.4.2.jar` |
| Resourceful Lib | `resourcefullib-forge-1.20.1-2.1.29.jar` |
| TerraBlender | `TerraBlender-forge-1.20.1-3.0.1.11.jar` |
| Twilight Forest | `twilightforest-1.20.1-4.3.2508-universal.jar` |
| Twilight Forest - Dungeons & Villages | `tf_dnv-1.2.3.jar` |
| Vanilla Backport *(worldgen disabled in `server/data/config/vanillabackport-common.toml`; Bundles of Bravery enabled)* | `VanillaBackport-forge-1.20.1-1.2.2.jar` |

#### `modpack/server-only/` (Server Only)
| Mod | Jar |
| :--- | :--- |
| Chunky | `Chunky-1.3.146.jar` |
| FerriteCore | `ferritecore-6.0.1-forge.jar` |
| LuckPerms | `LuckPerms-Forge-5.4.102.jar` |
| ModernFix | `modernfix-forge-5.27.91+mc1.20.1.jar` |
| Paradigm | `Paradigm-forge-1.20.1-2.5.4.jar` |
| Simple Backups | `SimpleBackups-1.20.1-3.1.24.jar` |

#### `modpack/client-only/` (Client Only)
| Mod | Jar |
| :--- | :--- |
| AppleSkin | `appleskin-forge-mc1.20.1-2.5.1.jar` |
| Better Ping Display | `BetterPingDisplay-1.20.1-1.1.jar` |
| Controlling | `Controlling-forge-1.20.1-12.0.2.jar` |
| Distant Horizons | `DistantHorizons-3.3.3-1.20.1-fabric-forge.jar` |
| Embeddium | `embeddium-0.3.31+mc1.20.1.jar` |
| JourneyMap | `journeymap-forge-1.20.1-6.0.7.jar` |
| Mouse Tweaks | `MouseTweaks-forge-mc1.20.1-2.25.1.jar` |
| Oculus | `oculus-mc1.20.1-1.8.0.jar` |
| Searchables | `Searchables-forge-1.20.1-1.0.3.jar` |

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
