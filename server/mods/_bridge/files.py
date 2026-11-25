"""Filesystem guards, hashing, and deterministic atomic placement helpers."""

from __future__ import annotations

import contextlib
import hashlib
import os
import stat
import tempfile
from collections.abc import Iterable, Mapping
from pathlib import Path

DEFAULT_FORBIDDEN_SUFFIXES: tuple[str, ...] = (
    ".jar",
    ".db",
    ".sqlite",
    ".log",
    ".gz",
    ".zip",
    ".tar",
    ".tgz",
    ".bak",
    ".tmp",
    ".lock",
)


def sha256_bytes(data: bytes) -> str:
    """Return the lowercase SHA-256 hex digest of `data`."""
    return hashlib.sha256(data).hexdigest()


def check_forbidden_entries(
    configs_dir: Path,
    forbidden_names: Iterable[str] = (),
    forbidden_suffixes: Iterable[str] = (),
    *,
    suffix_label: str = "archive/runtime",
) -> list[str]:
    """Verify `configs_dir` contains no symlinks, forbidden names, or forbidden suffixes."""
    errors: list[str] = []
    forbidden_name_set = set(forbidden_names)
    suffix_tuple = tuple(s.lower() for s in forbidden_suffixes)

    for name in sorted(forbidden_name_set):
        if (configs_dir / name).exists() or (configs_dir / name).is_symlink():
            errors.append(
                f"Forbidden file/directory present in configs/: {name}"
            )

    for entry in sorted(configs_dir.rglob("*")):
        rel = entry.relative_to(configs_dir).as_posix()
        if entry.is_symlink():
            errors.append(f"Symlinks are forbidden in configs/: {rel}")
            continue
        if entry.name in forbidden_name_set and rel != entry.name:
            errors.append(f"Forbidden file/directory present in configs/: {rel}")
        if entry.is_file() and suffix_tuple and entry.name.lower().endswith(suffix_tuple):
            errors.append(f"Forbidden {suffix_label} file present in configs/: {rel}")

    return errors


def collect_config_files(configs_dir: Path) -> tuple[dict[str, Path], list[str]]:
    """Return `({rel_posix: path}, errors)` for all non-symlink files in `configs_dir`."""
    files: dict[str, Path] = {}
    errors: list[str] = []
    for entry in sorted(configs_dir.rglob("*")):
        rel = entry.relative_to(configs_dir).as_posix()
        if entry.is_symlink():
            errors.append(f"Symlinks are forbidden in configs/: {rel}")
            continue
        if entry.is_file():
            files[rel] = entry
    return files, errors


def atomic_write_bytes(
    target_path: Path, data: bytes, default_mode: int = 0o664
) -> None:
    """Atomically write `data` to `target_path`, preserving existing mode and UID/GID."""
    target_path.parent.mkdir(parents=True, exist_ok=True)
    target_stat = target_path.stat() if target_path.exists() else None
    mode = stat.S_IMODE(target_stat.st_mode) if target_stat else default_mode

    fd, tmp_name = tempfile.mkstemp(
        prefix=f".{target_path.name}.",
        suffix=".tmp",
        dir=str(target_path.parent),
    )
    tmp_path = Path(tmp_name)
    try:
        with os.fdopen(fd, "wb") as handle:
            handle.write(data)
            handle.flush()
            os.fsync(handle.fileno())
        os.chmod(tmp_path, mode)
        if target_stat is not None and hasattr(os, "chown"):
            with contextlib.suppress(PermissionError):
                os.chown(tmp_path, target_stat.st_uid, target_stat.st_gid)
        os.replace(tmp_path, target_path)
    except Exception:
        if tmp_path.exists():
            tmp_path.unlink()
        raise


def sync_static_file(
    target_path: Path,
    src_bytes: bytes,
    dry_run: bool,
    default_mode: int = 0o664,
) -> bool:
    """Place `src_bytes` at `target_path` if missing or changed. Return True if changed."""
    if target_path.exists():
        dst_bytes = target_path.read_bytes()
        if sha256_bytes(src_bytes) == sha256_bytes(dst_bytes):
            return False

    if not dry_run:
        atomic_write_bytes(target_path, src_bytes, default_mode=default_mode)
    return True


def apply_static_files(
    static_files: Mapping[str, tuple[str, ...]],
    data_dir: Path,
    loaded_bytes: Mapping[str, bytes],
    dry_run: bool,
    default_mode: int = 0o664,
) -> tuple[int, int]:
    """Place validated static files from `loaded_bytes` into `data_dir`."""
    changed = 0
    unchanged = 0
    for rel, dst_parts in static_files.items():
        dst_path = data_dir.joinpath(*dst_parts)
        if sync_static_file(
            dst_path, loaded_bytes[rel], dry_run=dry_run, default_mode=default_mode
        ):
            action = "Would update (static)" if dry_run else "Updated (static)"
            print(f"  [{action}] {rel} -> {dst_path.relative_to(data_dir).as_posix()}")
            changed += 1
        else:
            unchanged += 1
    return changed, unchanged
