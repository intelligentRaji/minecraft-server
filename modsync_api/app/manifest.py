"""Deterministic SHA-256 modpack manifest builder and file resolver."""

from __future__ import annotations

import hashlib
import json
import re
import threading
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Literal, get_args

ClientCategory = Literal["server-client", "client-only"]
CLIENT_CATEGORIES: tuple[ClientCategory, ...] = get_args(ClientCategory)
SAFE_JAR_NAME_RE = re.compile(r"^[A-Za-z0-9._+-]+\.jar$")
HASH_CHUNK_SIZE = 1024 * 1024
MANIFEST_SCHEMA_VERSION = 1
VERSION_HASH_LENGTH = 16
MOD_DOWNLOAD_PREFIX = "/api/mods"


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
    recommended_version: str
    generated_at: str
    mods: tuple[ModEntry, ...]

    def find_mod(self, category: str, filename: str) -> ModEntry | None:
        for mod in self.mods:
            if mod.category == category and mod.filename == filename:
                return mod
        return None

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": MANIFEST_SCHEMA_VERSION,
            "version": self.version,
            "recommended_version": self.recommended_version,
            "generated_at": self.generated_at,
            "mod_count": len(self.mods),
            "mods": [mod.to_dict() for mod in self.mods],
        }

    def to_event(self, event_type: str) -> dict[str, object]:
        return {
            "type": event_type,
            "version": self.version,
            "mod_count": len(self.mods),
        }


def _hash_category_mods(mods: tuple[ModEntry, ...], category: ClientCategory) -> str:
    category_mods = [(m.category, m.filename, m.sha256, m.size) for m in mods if m.category == category]
    payload = json.dumps(category_mods, separators=(",", ":")).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()[:VERSION_HASH_LENGTH]


def compute_sha256(path: Path) -> str:
    """Return lowercase SHA-256 hex digest for a file."""
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        while chunk := handle.read(HASH_CHUNK_SIZE):
            digest.update(chunk)
    return digest.hexdigest()


def _is_safe_jar_file(path: Path) -> bool:
    return not path.is_symlink() and path.is_file() and bool(SAFE_JAR_NAME_RE.fullmatch(path.name))


def _resolve_category_dir(modpack_dir: Path, category: str) -> Path | None:
    if category not in CLIENT_CATEGORIES:
        return None
    raw_cat = modpack_dir / category
    if raw_cat.is_symlink() or not raw_cat.is_dir():
        return None
    resolved_root = modpack_dir.resolve()
    resolved_cat = raw_cat.resolve()
    if not resolved_cat.is_relative_to(resolved_root):
        return None
    return resolved_cat


def validate_jar_request(modpack_dir: Path, category: str, filename: str) -> Path | None:
    """Resolve a client-downloadable .jar safely; return None if invalid or missing."""
    if not SAFE_JAR_NAME_RE.fullmatch(filename):
        return None
    category_dir = _resolve_category_dir(modpack_dir, category)
    if category_dir is None:
        return None

    raw_candidate = category_dir / filename
    if not _is_safe_jar_file(raw_candidate):
        return None

    candidate = raw_candidate.resolve()
    if candidate.parent != category_dir:
        return None
    return candidate


class ManifestStore:
    """Thread-safe incremental scanner for modpack/server-client and modpack/client-only."""

    def __init__(self, modpack_dir: Path) -> None:
        self.modpack_dir = modpack_dir
        self._lock = threading.RLock()
        self._stat_cache: dict[tuple[str, str], tuple[int, int, str]] = {}
        self._current: Manifest | None = None

    @property
    def current(self) -> Manifest:
        with self._lock:
            if self._current is None:
                self._current, _ = self.refresh()
            return self._current

    def _build_entry(self, category: ClientCategory, entry: Path) -> ModEntry:
        stat_res = entry.stat()
        cache_key = (category, entry.name)
        cached = self._stat_cache.get(cache_key)
        if cached is not None and cached[0] == stat_res.st_size and cached[1] == stat_res.st_mtime_ns:
            sha256 = cached[2]
        else:
            sha256 = compute_sha256(entry)
            self._stat_cache[cache_key] = (stat_res.st_size, stat_res.st_mtime_ns, sha256)

        return ModEntry(
            filename=entry.name,
            category=category,
            sha256=sha256,
            size=stat_res.st_size,
            url=f"{MOD_DOWNLOAD_PREFIX}/{category}/{entry.name}",
        )

    def _scan_category(self, category: ClientCategory) -> list[ModEntry]:
        cat_dir = _resolve_category_dir(self.modpack_dir, category)
        if cat_dir is None:
            return []
        return [
            self._build_entry(category, entry)
            for entry in sorted(cat_dir.iterdir(), key=lambda p: p.name)
            if _is_safe_jar_file(entry)
        ]

    def _prune_cache(self, seen_keys: set[tuple[str, str]]) -> None:
        self._stat_cache = {key: value for key, value in self._stat_cache.items() if key in seen_keys}

    def refresh(self) -> tuple[Manifest, bool]:
        """Re-scan modpack directories, hashing only added or modified .jar files."""
        with self._lock:
            scanned = [entry for category in CLIENT_CATEGORIES for entry in self._scan_category(category)]
            self._prune_cache({(mod.category, mod.filename) for mod in scanned})

            sorted_mods = tuple(sorted(scanned, key=lambda mod: (mod.filename, mod.category)))
            version_hash = _hash_category_mods(sorted_mods, "server-client")
            recommended_hash = _hash_category_mods(sorted_mods, "client-only")

            prev = self._current
            if prev is not None and prev.version == version_hash and prev.recommended_version == recommended_hash:
                return prev, False

            manifest = Manifest(
                version=version_hash,
                recommended_version=recommended_hash,
                generated_at=datetime.now(UTC).isoformat(),
                mods=sorted_mods,
            )
            self._current = manifest
            return manifest, (prev is not None and prev.version != version_hash)
