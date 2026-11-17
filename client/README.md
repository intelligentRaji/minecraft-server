# ModSync Client

Standalone background Minecraft mod synchronizer with WebSocket push updates and a system tray UI.

## For Players (Standalone Binary)

1. Download `ModSync.exe` (Windows) or `ModSync-linux` (Linux) from GitHub Releases.
2. Double-click `ModSync.exe`.
3. On first launch, enter your server's ModSync URL (e.g. `https://mods.yourdomain.com`) and pick your Minecraft launcher's `mods` folder (e.g. Modrinth App profile `mods/`).
4. ModSync stays in your system tray:
   - **Green:** Mods are up to date and listening for instant server updates.
   - **Blue:** Downloading / checking mods.
   - **Amber:** Update downloaded and staged while Minecraft is open (applied automatically as soon as you close the game).
   - **Red:** Cannot reach the server (retries automatically).

## Running From Source (Development)

```bash
cd client
uv sync
uv run modsync --headless --server-url https://mods.yourdomain.com --mods-dir /path/to/mods
```

## Building Standalone Executable

```bash
cd client
uv sync --group dev
uv run pyinstaller modsync.spec --clean --noconfirm
```
