"""Remote manifest models, validation, and SHA-256 hashing utilities."""

from __future__ import annotations

import hashlib
import re
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Literal

ClientCategory = Literal["server-client", "client-only"]
SERVER_CLIENT_CATEGORY: ClientCategory = "server-client"
CLIENT_ONLY_CATEGORY: ClientCategory = "client-only"

SAFE_JAR_NAME_RE = re.compile(r"^[A-Za-z0-9._+-]+\.jar$")
SHA256_HEX_RE = re.compile(r"^[0-9a-f]{64}$")
HASH_CHUNK_SIZE = 1024 * 1024
MANIFEST_ENDPOINT_PATH = "/api/manifest"


@dataclass(frozen=True)
class RemoteMod:
    """Single mod entry parsed from the remote ModSync manifest."""

    filename: str
    category: str
    sha256: str
    size: int
    url: str


@dataclass(frozen=True)
class RemoteManifest:
    """Validated remote manifest snapshot."""

    version: str
    mods: tuple[RemoteMod, ...]


def compute_sha256(path: Path) -> str:
    """Return lowercase SHA-256 hex digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _parse_mod_entry(item: object) -> RemoteMod:
    if not isinstance(item, dict):
        raise ValueError("Invalid manifest entry: expected object")
    filename = str(item.get("filename", ""))
    if not SAFE_JAR_NAME_RE.fullmatch(filename):
        raise ValueError(f"Unsafe or invalid mod filename in manifest: {filename!r}")
    sha256 = str(item.get("sha256", "")).lower()
    if not SHA256_HEX_RE.fullmatch(sha256):
        raise ValueError(f"Invalid sha256 for {filename!r}")
    url = str(item.get("url", "")).strip()
    if not url:
        raise ValueError(f"Missing download URL for {filename!r}")
    return RemoteMod(
        filename=filename,
        category=str(item.get("category", "")),
        sha256=sha256,
        size=int(item.get("size", 0)),
        url=url,
    )


def parse_manifest(payload: dict[str, Any]) -> RemoteManifest:
    """Validate and parse manifest JSON from modsync-api."""
    version = str(payload.get("version", "")).strip()
    raw_mods = payload.get("mods")
    if not version or not isinstance(raw_mods, list):
        raise ValueError("Invalid manifest payload: missing 'version' or 'mods' list")
    return RemoteManifest(
        version=version,
        mods=tuple(_parse_mod_entry(item) for item in raw_mods),
    )
