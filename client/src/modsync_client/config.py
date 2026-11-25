"""Cross-platform configuration management and launcher mods-folder discovery."""

from __future__ import annotations

import json
import os
import sys
from dataclasses import asdict, dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qs, urlencode, urlparse, urlunparse

DEFAULT_POLL_FALLBACK_SECONDS = 300
INVITE_URL_SCHEME = "modsync"
HTTP_URL_SCHEMES = frozenset({"http", "https"})
VALID_URL_SCHEMES = frozenset({"http", "https", "ws", "wss"})
SECURE_URL_SCHEMES = frozenset({"https", "wss"})
WS_ENDPOINT_PATH = "/ws"
PROFILE_MODS_SUBPATHS = (
    Path("mods"),
    Path("minecraft") / "mods",
    Path(".minecraft") / "mods",
)


@dataclass(frozen=True)
class Config:
    """Persisted ModSync client configuration."""

    server_url: str
    mods_dir: str
    client_token: str = ""
    poll_fallback_seconds: int = DEFAULT_POLL_FALLBACK_SECONDS

    @property
    def normalized_server_url(self) -> str:
        return self.server_url.strip().rstrip("/")

    @property
    def mods_path(self) -> Path:
        return Path(self.mods_dir).expanduser()

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    @classmethod
    def from_dict(cls, raw: dict[str, Any]) -> Config | None:
        server_url = str(raw.get("server_url", "")).strip()
        mods_dir = str(raw.get("mods_dir", "")).strip()
        if not server_url or not mods_dir:
            return None
        return cls(
            server_url=server_url,
            mods_dir=mods_dir,
            client_token=str(raw.get("client_token", "")),
            poll_fallback_seconds=int(
                raw.get("poll_fallback_seconds", DEFAULT_POLL_FALLBACK_SECONDS)
            ),
        )

    @classmethod
    def from_env(cls) -> Config | None:
        env_url = os.environ.get("MODSYNC_SERVER_URL", "").strip().rstrip("/")
        env_mods = os.environ.get("MODSYNC_MODS_DIR", "").strip()
        if not env_url or not env_mods:
            return None
        return cls(
            server_url=env_url,
            mods_dir=env_mods,
            client_token=os.environ.get("MODSYNC_CLIENT_TOKEN", "").strip(),
        )


# Backward-compatible alias
AppConfig = Config


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


def _scan_profile_roots(roots: list[Path]) -> list[Path]:
    found: list[Path] = []
    for root in roots:
        if not root.is_dir():
            continue
        for child in sorted(root.iterdir()):
            for subpath in PROFILE_MODS_SUBPATHS:
                candidate = child / subpath
                if candidate.is_dir():
                    found.append(candidate)
    return found


def _windows_mods_candidates(home: Path) -> list[Path]:
    appdata = Path(os.environ.get("APPDATA", str(home / "AppData" / "Roaming")))
    candidates = _scan_profile_roots(
        [
            appdata / "ModrinthApp" / "profiles",
            appdata / "PrismLauncher" / "instances",
            appdata / "MultiMC" / "instances",
        ]
    )

    curseforge_root = home / "curseforge" / "minecraft" / "Instances"
    if curseforge_root.is_dir():
        for child in sorted(curseforge_root.iterdir()):
            mods = child / "mods"
            if mods.is_dir():
                candidates.append(mods)

    vanilla = appdata / ".minecraft" / "mods"
    if vanilla.is_dir():
        candidates.append(vanilla)
    return candidates


def _unix_mods_candidates(home: Path) -> list[Path]:
    candidates = _scan_profile_roots(
        [
            home / ".local" / "share" / "ModrinthApp" / "profiles",
            home / ".local" / "share" / "PrismLauncher" / "instances",
            home / ".var" / "app" / "com.modrinth.ModrinthApp" / "data" / "ModrinthApp" / "profiles",
            home / ".var" / "app" / "org.prismlauncher.PrismLauncher" / "data" / "PrismLauncher" / "instances",
        ]
    )
    vanilla = home / ".minecraft" / "mods"
    if vanilla.is_dir():
        candidates.append(vanilla)
    return candidates


def _deduplicate_paths(paths: list[Path]) -> list[Path]:
    unique: list[Path] = []
    seen: set[Path] = set()
    for path in paths:
        resolved = path.resolve()
        if resolved not in seen:
            seen.add(resolved)
            unique.append(path)
    return unique


def detect_minecraft_dirs() -> list[Path]:
    """Discover likely Minecraft profile/instance root folders (parent of mods/)."""
    home = Path.home()
    mods_candidates = (
        _windows_mods_candidates(home)
        if sys.platform == "win32"
        else _unix_mods_candidates(home)
    )
    return _deduplicate_paths([mods_dir.parent for mods_dir in mods_candidates])


def resolve_mods_dir(selected_dir: Path | str) -> Path:
    """Resolve the mods/ directory from a selected Minecraft folder or mods/ itself."""
    path = Path(selected_dir).expanduser()
    if path.name.lower() == "mods":
        return path
    for nested in (Path(".minecraft") / "mods", Path("minecraft") / "mods"):
        candidate = path / nested
        if candidate.is_dir():
            return candidate
    if (path / ".minecraft").is_dir():
        return path / ".minecraft" / "mods"
    return path / "mods"


def build_invite_url(server_url: str, client_token: str = "") -> str:
    """Build a shareable modsync://connect?... invite URI for players."""
    normalized = server_url.strip().rstrip("/")
    parsed = urlparse(normalized)
    if parsed.scheme not in HTTP_URL_SCHEMES or not parsed.netloc:
        raise ValueError(
            f"Invalid server URL: {server_url!r} (expected https://... or http://...)"
        )
    params: dict[str, str] = {"url": normalized}
    token = client_token.strip()
    if token:
        params["token"] = token
    return f"{INVITE_URL_SCHEME}://connect?{urlencode(params)}"


def parse_server_input(raw: str) -> tuple[str, str | None]:
    """Parse either a modsync://connect?... invite link or an http(s):// server URL."""
    text = raw.strip()
    if not text:
        raise ValueError("Server URL or invite link is required.")
    parsed = urlparse(text)
    if parsed.scheme.lower() == INVITE_URL_SCHEME:
        params = parse_qs(parsed.query)
        url_values = params.get("url") or []
        target_url = url_values[0].strip().rstrip("/") if url_values else ""
        target_parsed = urlparse(target_url)
        if target_parsed.scheme not in HTTP_URL_SCHEMES or not target_parsed.netloc:
            raise ValueError(
                f"Invalid invite link: missing or invalid 'url' parameter in {raw!r}"
            )
        token_values = params.get("token") or []
        token = token_values[0].strip() if token_values and token_values[0].strip() else None
        return target_url, token

    if parsed.scheme not in HTTP_URL_SCHEMES or not parsed.netloc:
        raise ValueError(
            f"Invalid server URL or invite link: {raw!r} "
            "(expected modsync://connect?... or https://...)"
        )
    return text.rstrip("/"), None


def build_ws_url(server_url: str, client_token: str = "") -> str:
    """Convert an http(s):// server base URL to a ws(s)://.../ws WebSocket URL."""
    parsed = urlparse(server_url.strip())
    if parsed.scheme not in VALID_URL_SCHEMES or not parsed.netloc:
        raise ValueError(
            f"Invalid server URL: {server_url!r} (expected https://... or http://...)"
        )

    ws_scheme = "wss" if parsed.scheme in SECURE_URL_SCHEMES else "ws"
    base_path = parsed.path.rstrip("/")
    ws_path = (
        f"{base_path}{WS_ENDPOINT_PATH}"
        if not base_path.endswith(WS_ENDPOINT_PATH)
        else base_path
    )
    query = urlencode({"token": client_token}) if client_token else parsed.query
    return urlunparse((ws_scheme, parsed.netloc, ws_path, "", query, ""))


def load_config(path: Path | None = None) -> Config | None:
    """Load persisted configuration if present and valid."""
    cfg_path = path or default_config_path()
    if not cfg_path.is_file():
        return None
    raw = json.loads(cfg_path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        return None
    return Config.from_dict(raw)


def save_config(config: Config, path: Path | None = None) -> Path:
    """Persist configuration atomically."""
    cfg_path = path or default_config_path()
    cfg_path.parent.mkdir(parents=True, exist_ok=True)
    tmp_path = cfg_path.with_suffix(".tmp")
    tmp_path.write_text(json.dumps(config.to_dict(), indent=2) + "\n", encoding="utf-8")
    os.replace(tmp_path, cfg_path)
    return cfg_path
