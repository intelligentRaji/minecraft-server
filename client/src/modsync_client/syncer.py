"""Manifest-driven mod synchronizer with SHA-256 verification and safe staging."""

from __future__ import annotations

import json
import logging
import os
import shutil
import tomllib
import zipfile
from dataclasses import dataclass
from enum import Enum
from pathlib import Path
from typing import Callable
from urllib.parse import urljoin

from .manifest import (
    CLIENT_ONLY_CATEGORY,
    HASH_CHUNK_SIZE,
    MANIFEST_ENDPOINT_PATH,
    SAFE_JAR_NAME_RE,
    SERVER_CLIENT_CATEGORY,
    RemoteManifest,
    RemoteMod,
    compute_sha256,
    parse_manifest,
)
from .process import MC_CMDLINE_MARKERS, default_is_minecraft_running
from .transport import HttpTransport, HttpxTransport

logger = logging.getLogger("modsync_client.syncer")

MANAGED_STATE_FILENAME = ".modsync-managed.json"


def _extract_forge_mod_ids(jar_path: Path) -> frozenset[str]:
    """Read declared Forge modId values from META-INF/mods.toml inside a jar."""
    try:
        with zipfile.ZipFile(jar_path) as archive:
            with archive.open("META-INF/mods.toml") as handle:
                data = tomllib.loads(handle.read().decode("utf-8", errors="replace"))
    except (OSError, zipfile.BadZipFile, KeyError, tomllib.TOMLDecodeError):
        return frozenset()
    mods = data.get("mods")
    if not isinstance(mods, list):
        return frozenset()
    return frozenset(
        str(entry["modId"]).strip().lower()
        for entry in mods
        if isinstance(entry, dict) and entry.get("modId")
    )

__all__ = [
    "CLIENT_ONLY_CATEGORY",
    "HASH_CHUNK_SIZE",
    "HttpTransport",
    "HttpxTransport",
    "MC_CMDLINE_MARKERS",
    "ModSyncer",
    "RemoteManifest",
    "RemoteMod",
    "SAFE_JAR_NAME_RE",
    "SERVER_CLIENT_CATEGORY",
    "SyncResult",
    "SyncStatus",
    "compute_sha256",
    "default_is_minecraft_running",
    "parse_manifest",
]


class SyncStatus(str, Enum):
    IDLE = "idle"
    SYNCING = "syncing"
    SYNCED = "synced"
    STAGED_WAITING_MC = "staged_waiting_mc"
    ERROR = "error"


@dataclass(frozen=True)
class SyncResult:
    status: SyncStatus
    version: str
    mod_count: int
    added: tuple[str, ...] = ()
    updated: tuple[str, ...] = ()
    removed: tuple[str, ...] = ()
    message: str = ""


class ModSyncer:
    """Synchronizes a local Minecraft mods/ folder against modsync-api."""

    def __init__(
        self,
        *,
        server_url: str,
        mods_dir: Path,
        staging_dir: Path,
        client_token: str = "",
        transport: HttpTransport | None = None,
        mc_running_check: Callable[[], bool] | None = None,
    ) -> None:
        self.server_url = server_url.strip().rstrip("/")
        self.mods_dir = mods_dir
        self.staging_dir = staging_dir
        self._owns_transport = transport is None
        self.transport: HttpTransport = (
            transport if transport is not None else HttpxTransport(client_token=client_token)
        )
        self.mc_running_check = mc_running_check or default_is_minecraft_running

        self._hash_cache: dict[Path, tuple[int, int, str]] = {}
        self._mod_id_cache: dict[Path, tuple[int, int, frozenset[str]]] = {}
        self._pending_sync: tuple[RemoteManifest, str] | None = None

    @property
    def _managed_state_path(self) -> Path:
        return self.mods_dir / MANAGED_STATE_FILENAME

    def _load_managed_names(self) -> set[str]:
        path = self._managed_state_path
        if not path.is_file():
            return set()
        try:
            raw = json.loads(path.read_text(encoding="utf-8"))
        except (OSError, json.JSONDecodeError):
            return set()
        names = raw.get("managed") if isinstance(raw, dict) else None
        if not isinstance(names, list):
            return set()
        return {str(name) for name in names if isinstance(name, str)}

    def _save_managed_names(self, names: set[str]) -> None:
        self.mods_dir.mkdir(parents=True, exist_ok=True)
        path = self._managed_state_path
        tmp_path = path.with_suffix(".tmp")
        payload = {"managed": sorted(names)}
        tmp_path.write_text(json.dumps(payload, indent=2) + "\n", encoding="utf-8")
        os.replace(tmp_path, path)

    def _local_mod_ids(self, path: Path) -> frozenset[str]:
        try:
            st = path.stat()
        except OSError:
            return frozenset()
        cached = self._mod_id_cache.get(path)
        if cached is not None and cached[0] == st.st_size and cached[1] == st.st_mtime_ns:
            return cached[2]
        mod_ids = _extract_forge_mod_ids(path)
        self._mod_id_cache[path] = (st.st_size, st.st_mtime_ns, mod_ids)
        return mod_ids

    def close(self) -> None:
        if self._owns_transport and hasattr(self.transport, "close"):
            self.transport.close()  # type: ignore[attr-defined]

    def _local_sha256(self, path: Path) -> str:
        st = path.stat()
        cached = self._hash_cache.get(path)
        if cached is not None and cached[0] == st.st_size and cached[1] == st.st_mtime_ns:
            return cached[2]
        digest = compute_sha256(path)
        self._hash_cache[path] = (st.st_size, st.st_mtime_ns, digest)
        return digest

    def _list_local_jars(self) -> dict[str, Path]:
        if not self.mods_dir.is_dir():
            return {}
        return {
            entry.name: entry
            for entry in self.mods_dir.iterdir()
            if entry.is_file() and entry.suffix == ".jar"
        }

    def _resolve_download_url(self, mod_url: str) -> str:
        if mod_url.startswith(("http://", "https://")):
            return mod_url
        return urljoin(f"{self.server_url}/", mod_url.lstrip("/"))

    @staticmethod
    def _is_staged_valid(staged_path: Path, expected_sha256: str) -> bool:
        return staged_path.is_file() and compute_sha256(staged_path) == expected_sha256

    def _stage_mod(self, mod: RemoteMod) -> Path:
        self.staging_dir.mkdir(parents=True, exist_ok=True)
        staged_path = self.staging_dir / mod.filename
        if self._is_staged_valid(staged_path, mod.sha256):
            return staged_path

        part_path = self.staging_dir / f".{mod.filename}.part"
        part_path.unlink(missing_ok=True)

        download_url = self._resolve_download_url(mod.url)
        self.transport.download_to(download_url, part_path)

        actual_sha = compute_sha256(part_path)
        if actual_sha != mod.sha256:
            part_path.unlink(missing_ok=True)
            raise ValueError(
                f"SHA-256 mismatch for {mod.filename}: expected {mod.sha256}, got {actual_sha}"
            )
        os.replace(part_path, staged_path)
        return staged_path

    def _compute_downloads(
        self,
        manifest: RemoteManifest,
        target_category: str,
    ) -> tuple[list[RemoteMod], list[RemoteMod], list[RemoteMod], dict[str, Path]]:
        local_jars = self._list_local_jars()
        target_mods = [m for m in manifest.mods if m.category == target_category]

        to_add: list[RemoteMod] = []
        to_update: list[RemoteMod] = []
        for mod in target_mods:
            existing = local_jars.get(mod.filename)
            if existing is None:
                to_add.append(mod)
            elif self._local_sha256(existing) != mod.sha256:
                to_update.append(mod)
        return to_add, to_update, target_mods, local_jars

    def _compute_removals(
        self,
        manifest: RemoteManifest,
        target_mods: list[RemoteMod],
        local_jars: dict[str, Path],
    ) -> list[str]:
        protected_names = {m.filename for m in manifest.mods}
        managed_names = self._load_managed_names()

        target_mod_ids: set[str] = set()
        for mod in target_mods:
            staged_path = self.staging_dir / mod.filename
            source_path = staged_path if staged_path.is_file() else local_jars.get(mod.filename)
            if source_path is not None:
                target_mod_ids.update(self._local_mod_ids(source_path))

        to_remove: list[str] = []
        for name, jar_path in sorted(local_jars.items()):
            if name in protected_names:
                continue
            if name in managed_names or (
                target_mod_ids and bool(self._local_mod_ids(jar_path) & target_mod_ids)
            ):
                to_remove.append(name)
        return to_remove

    def _remove_jars(self, filenames: list[str]) -> None:
        for name in filenames:
            target = self.mods_dir / name
            target.unlink(missing_ok=True)
            self._hash_cache.pop(target, None)
            self._mod_id_cache.pop(target, None)

    def _promote_staged_jar(self, mod: RemoteMod) -> None:
        staged_path = self.staging_dir / mod.filename
        dest_path = self.mods_dir / mod.filename
        try:
            os.replace(staged_path, dest_path)
        except OSError:
            tmp_dest = self.mods_dir / f".{mod.filename}.tmp"
            shutil.copy2(staged_path, tmp_dest)
            os.replace(tmp_dest, dest_path)
            staged_path.unlink(missing_ok=True)
        st = dest_path.stat()
        self._hash_cache[dest_path] = (st.st_size, st.st_mtime_ns, mod.sha256)
        self._mod_id_cache.pop(dest_path, None)

    def _apply_changes(
        self,
        manifest: RemoteManifest,
        target_mods: list[RemoteMod],
        to_add: list[RemoteMod],
        to_update: list[RemoteMod],
        to_remove: list[str],
    ) -> SyncResult:
        self.mods_dir.mkdir(parents=True, exist_ok=True)
        self._remove_jars(to_remove)
        for mod in [*to_add, *to_update]:
            self._promote_staged_jar(mod)

        managed = (self._load_managed_names() - set(to_remove)) | {
            m.filename for m in target_mods if (self.mods_dir / m.filename).is_file()
        }
        self._save_managed_names(managed)

        self._pending_sync = None
        target_count = len(target_mods)
        added_names = tuple(m.filename for m in to_add)
        updated_names = tuple(m.filename for m in to_update)
        removed_names = tuple(to_remove)
        return SyncResult(
            status=SyncStatus.SYNCED,
            version=manifest.version,
            mod_count=target_count,
            added=added_names,
            updated=updated_names,
            removed=removed_names,
            message=self._format_summary(target_count, added_names, updated_names, removed_names),
        )

    @staticmethod
    def _format_summary(
        target_count: int,
        added: tuple[str, ...],
        updated: tuple[str, ...],
        removed: tuple[str, ...],
    ) -> str:
        parts = []
        if added:
            parts.append(f"+{len(added)} added")
        if updated:
            parts.append(f"~{len(updated)} updated")
        if removed:
            parts.append(f"-{len(removed)} removed")
        if not parts:
            return f"Synced ({target_count} mods)"
        return f"Synced ({', '.join(parts)}; {target_count} total)"

    def _fetch_manifest(self) -> RemoteManifest:
        payload = self.transport.get_json(f"{self.server_url}{MANIFEST_ENDPOINT_PATH}")
        return parse_manifest(payload)

    def _record_present_managed(
        self,
        target_mods: list[RemoteMod],
        local_jars: dict[str, Path],
    ) -> None:
        if not target_mods or not self.mods_dir.is_dir():
            return
        managed = self._load_managed_names()
        present_target = {m.filename for m in target_mods if m.filename in local_jars}
        if not present_target.issubset(managed):
            self._save_managed_names(managed | present_target)

    def try_apply_staged(self) -> SyncResult | None:
        """Apply previously staged updates if Minecraft is no longer running."""
        if self._pending_sync is None or self.mc_running_check():
            return None

        manifest, target_category = self._pending_sync
        to_add, to_update, target_mods, local_jars = self._compute_downloads(
            manifest, target_category
        )
        for mod in [*to_add, *to_update]:
            staged_path = self.staging_dir / mod.filename
            if not self._is_staged_valid(staged_path, mod.sha256):
                self._stage_mod(mod)
        to_remove = self._compute_removals(manifest, target_mods, local_jars)
        return self._apply_changes(manifest, target_mods, to_add, to_update, to_remove)

    def _sync_category(self, target_category: str) -> SyncResult:
        manifest = self._fetch_manifest()
        to_add, to_update, target_mods, local_jars = self._compute_downloads(
            manifest, target_category
        )
        for mod in [*to_add, *to_update]:
            self._stage_mod(mod)

        to_remove = self._compute_removals(manifest, target_mods, local_jars)
        target_count = len(target_mods)
        if not to_add and not to_update and not to_remove:
            self._record_present_managed(target_mods, local_jars)
            self._pending_sync = None
            return SyncResult(
                status=SyncStatus.SYNCED,
                version=manifest.version,
                mod_count=target_count,
                message=f"Synced ({target_count} mods)",
            )

        if self.mc_running_check():
            self._pending_sync = (manifest, target_category)
            pending_count = len(to_add) + len(to_update) + len(to_remove)
            return SyncResult(
                status=SyncStatus.STAGED_WAITING_MC,
                version=manifest.version,
                mod_count=target_count,
                added=tuple(m.filename for m in to_add),
                updated=tuple(m.filename for m in to_update),
                removed=tuple(to_remove),
                message=f"Update staged ({pending_count} change(s)) — close Minecraft to apply",
            )

        return self._apply_changes(manifest, target_mods, to_add, to_update, to_remove)

    def sync_once(self) -> SyncResult:
        """Fetch remote manifest and synchronize mandatory server-client mods."""
        return self._sync_category(SERVER_CLIENT_CATEGORY)

    def install_recommended(self) -> SyncResult:
        """Fetch remote manifest and install/replace optional client-only mods on demand."""
        return self._sync_category(CLIENT_ONLY_CATEGORY)
