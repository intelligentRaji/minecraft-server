"""Deterministic SHA-256 modpack manifest builder and file resolver."""

from __future__ import annotations

import hashlib
import json
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Literal

ClientCategory = Literal["server-client", "client-only"]
CLIENT_CATEGORIES: tuple[ClientCategory, ...] = ("server-client", "client-only")
SAFE_JAR_NAME_RE = re.compile(r"^[A-Za-z0-9._+-]+\.jar$")
HASH_CHUNK_SIZE = 1024 * 1024


@dataclass(frozen=True)
class ModEntry:
    """Single downloadable client mod entry in the manifest."""

    filename: str
    category: ClientCategory
    sha256: str
    size: int
    url: str

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass(frozen=True)
class Manifest:
    """Immutable snapshot of all client-facing mods."""

    version: str
    generated_at: str
    mods: tuple[ModEntry, ...]

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": 1,
            "version": self.version,
            "generated_at": self.generated_at,
            "mod_count": len(self.mods),
            "mods": [mod.to_dict() for mod in self.mods],
        }


def compute_sha256(path: Path) -> str:
    """Return lowercase SHA-256 hex digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def validate_jar_request(modpack_dir: Path, category: str, filename: str) -> Path | None:
    """Resolve a client-downloadable .jar safely; return None if invalid or missing."""
    if category not in CLIENT_CATEGORIES:
        return None
    if not SAFE_JAR_NAME_RE.fullmatch(filename):
        return None

    category_dir = (modpack_dir / category).resolve()
    candidate = (category_dir / filename).resolve()
    if candidate.parent != category_dir:
        return None
    if candidate.is_symlink() or not candidate.is_file():
        return None
    return candidate


class ManifestStore:
    """Thread-safe incremental scanner for modpack/server-client and modpack/client-only."""

    def __init__(self, modpack_dir: Path) -> None:
        self.modpack_dir = modpack_dir
        self._stat_cache: dict[tuple[str, str], tuple[int, int, str]] = {}
        self._current: Manifest | None = None

    @property
    def current(self) -> Manifest:
        if self._current is None:
            self._current, _ = self.refresh()
        return self._current

    def refresh(self) -> tuple[Manifest, bool]:
        """Re-scan modpack directories, hashing only added or modified .jar files."""
        entries_by_name: dict[str, ModEntry] = {}
        seen_keys: set[tuple[str, str]] = set()

        for category in CLIENT_CATEGORIES:
            cat_dir = self.modpack_dir / category
            if not cat_dir.is_dir():
                continue

            for entry in sorted(cat_dir.iterdir(), key=lambda p: p.name):
                if entry.is_symlink() or not entry.is_file():
                    continue
                if not SAFE_JAR_NAME_RE.fullmatch(entry.name):
                    continue

                stat_res = entry.stat()
                cache_key = (category, entry.name)
                seen_keys.add(cache_key)
                cached = self._stat_cache.get(cache_key)
                if cached is not None and cached[0] == stat_res.st_size and cached[1] == stat_res.st_mtime_ns:
                    sha256 = cached[2]
                else:
                    sha256 = compute_sha256(entry)
                    self._stat_cache[cache_key] = (stat_res.st_size, stat_res.st_mtime_ns, sha256)

                entries_by_name[entry.name] = ModEntry(
                    filename=entry.name,
                    category=category,
                    sha256=sha256,
                    size=stat_res.st_size,
                    url=f"/api/mods/{category}/{entry.name}",
                )

        # Prune removed files from cache
        for stale_key in list(self._stat_cache.keys()):
            if stale_key not in seen_keys:
                del self._stat_cache[stale_key]

        sorted_mods = tuple(entries_by_name[name] for name in sorted(entries_by_name))
        version_payload = json.dumps(
            [(m.category, m.filename, m.sha256, m.size) for m in sorted_mods],
            separators=(",", ":"),
        ).encode("utf-8")
        version_hash = hashlib.sha256(version_payload).hexdigest()[:16]

        prev_version = self._current.version if self._current is not None else None
        if prev_version == version_hash and self._current is not None:
            return self._current, False

        manifest = Manifest(
            version=version_hash,
            generated_at=datetime.now(timezone.utc).isoformat(),
            mods=sorted_mods,
        )
        self._current = manifest
        return manifest, (prev_version is not None and prev_version != version_hash)
