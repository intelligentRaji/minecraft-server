"""Cross-platform configuration management and launcher mods-folder discovery."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from urllib.parse import urlencode, urlparse, urlunparse


DEFAULT_SERVER_URL = os.environ.get("MODSYNC_DEFAULT_SERVER_URL", "")


@dataclass
class AppConfig:
    """Persisted ModSync client configuration."""

    server_url: str
    mods_dir: str
    client_token: str = ""
    poll_fallback_seconds: int = 300

    @property
    def normalized_server_url(self) -> str:
        return self.server_url.strip().rstrip("/")

    @property
    def mods_path(self) -> Path:
        return Path(self.mods_dir).expanduser()


def default_data_dir() -> Path:
    """Return platform-appropriate directory for ModSync config and staging cache."""
    if sys.platform == "win32":
        appdata = os.environ.get("APPDATA")
        base = Path(appdata) if appdata else Path.home() / "AppData" / "Roaming"
        return base / "ModSync"
    if sys.platform == "darwin":
        return Path.home() / "Library" / "Application Support" / "ModSync"
    xdg = os.environ.get("XDG_CONFIG_HOME")
    base = Path(xdg) if xdg else Path.home() / ".config"
    return base / "modsync"


def default_config_path() -> Path:
    return default_data_dir() / "config.json"


def default_staging_dir() -> Path:
    return default_data_dir() / "staging"


def detect_mods_dirs() -> list[Path]:
    """Discover likely Minecraft launcher mods/ directories on the current OS."""
    candidates: list[Path] = []
    home = Path.home()

    if sys.platform == "win32":
        appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
        patterns = [
            appdata / "ModrinthApp" / "profiles",
            appdata / "PrismLauncher" / "instances",
            appdata / "MultiMC" / "instances",
        ]
        for root in patterns:
            if root.is_dir():
                for child in sorted(root.iterdir()):
                    for sub in (child / "mods", child / "minecraft" / "mods", child / ".minecraft" / "mods"):
                        if sub.is_dir():
                            candidates.append(sub)

        curseforge_root = home / "curseforge" / "minecraft" / "Instances"
        if curseforge_root.is_dir():
            for child in sorted(curseforge_root.iterdir()):
                mods = child / "mods"
                if mods.is_dir():
                    candidates.append(mods)

        vanilla = appdata / ".minecraft" / "mods"
        if vanilla.is_dir():
            candidates.append(vanilla)
    else:
        roots = [
            home / ".local" / "share" / "ModrinthApp" / "profiles",
            home / ".local" / "share" / "PrismLauncher" / "instances",
            home / ".var" / "app" / "com.modrinth.ModrinthApp" / "data" / "ModrinthApp" / "profiles",
            home / ".var" / "app" / "org.prismlauncher.PrismLauncher" / "data" / "PrismLauncher" / "instances",
        ]
        for root in roots:
            if root.is_dir():
                for child in sorted(root.iterdir()):
                    for sub in (child / "mods", child / "minecraft" / "mods", child / ".minecraft" / "mods"):
                        if sub.is_dir():
                            candidates.append(sub)

        vanilla = home / ".minecraft" / "mods"
        if vanilla.is_dir():
            candidates.append(vanilla)

    # Deduplicate preserving order
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in candidates:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def build_ws_url(server_url: str, client_token: str = "") -> str:
    """Convert an http(s):// server base URL to a ws(s)://.../ws WebSocket URL."""
    parsed = urlparse(server_url.strip())
    if parsed.scheme not in {"http", "https", "ws", "wss"} or not parsed.netloc:
        raise ValueError(f"Invalid server URL: {server_url!r} (expected https://... or http://...)")

    ws_scheme = "wss" if parsed.scheme in {"https", "wss"} else "ws"
    base_path = parsed.path.rstrip("/")
    ws_path = f"{base_path}/ws" if not base_path.endswith("/ws") else base_path
    query = urlencode({"token": client_token}) if client_token else parsed.query
    return urlunparse((ws_scheme, parsed.netloc, ws_path, "", query, ""))


def load_config(path: Path | None = None) -> AppConfig | None:
    """Load persisted configuration if present and valid."""
    cfg_path = path or default_config_path()
    if not cfg_path.is_file():
        return None
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    server_url = str(raw.get("server_url", "")).strip()
    mods_dir = str(raw.get("mods_dir", "")).strip()
    if not server_url or not mods_dir:
        return None
    return AppConfig(
        server_url=server_url,
        mods_dir=mods_dir,
        client_token=str(raw.get("client_token", "")),
        poll_fallback_seconds=int(raw.get("poll_fallback_seconds", 300)),
    )


def save_config(config: AppConfig, path: Path | None = None) -> Path:
    """Persist configuration atomically."""
    cfg_path = path or default_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cfg_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(asdict(config), indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, cfg_path)
    return cfg_path
