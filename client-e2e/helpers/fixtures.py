"""Typed test fixture entities and config snapshot helpers for client E2E tests."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from dataclasses import dataclass
from pathlib import Path

CATEGORY_SERVER_CLIENT = "server-client"
CATEGORY_CLIENT_ONLY = "client-only"
CATEGORY_SERVER_ONLY = "server-only"
MODPACK_CATEGORIES = (
    CATEGORY_SERVER_CLIENT,
    CATEGORY_CLIENT_ONLY,
    CATEGORY_SERVER_ONLY,
)

JAR_MANIFEST_PATH = "META-INF/MANIFEST.MF"
JAR_MANIFEST_CONTENT = "Manifest-Version: 1.0\n"
JAR_MODS_TOML_PATH = "META-INF/mods.toml"
FORGE_LOADER_VERSION = "[47,)"
DEFAULT_MOD_LICENSE = "MIT"

CFG_KEY_SERVER_URL = "server_url"
CFG_KEY_MODS_DIR = "mods_dir"
CFG_KEY_CLIENT_TOKEN = "client_token"


def make_jar_bytes(mod_id: str, version: str) -> bytes:
    """Create a valid Forge 1.20.1 mod JAR archive with META-INF/mods.toml."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", compression=zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(JAR_MANIFEST_PATH, JAR_MANIFEST_CONTENT)
        archive.writestr(
            JAR_MODS_TOML_PATH,
            (
                'modLoader="javafml"\n'
                f'loaderVersion="{FORGE_LOADER_VERSION}"\n'
                f'license="{DEFAULT_MOD_LICENSE}"\n'
                "[[mods]]\n"
                f'modId="{mod_id}"\n'
                f'version="{version}"\n'
                f'displayName="{mod_id.title()}"\n'
            ),
        )
    return buf.getvalue()


def compute_sha256(data_or_path: bytes | Path) -> str:
    """Compute lowercase SHA-256 hex digest of bytes or a file on disk."""
    payload = data_or_path.read_bytes() if isinstance(data_or_path, Path) else data_or_path
    return hashlib.sha256(payload).hexdigest()


@dataclass(frozen=True)
class ModFixture:
    """Represents a deterministic Forge mod JAR fixture in a modpack category."""

    category: str
    mod_id: str
    version: str
    filename: str

    def jar_bytes(self) -> bytes:
        return make_jar_bytes(self.mod_id, self.version)

    def sha256(self) -> str:
        return compute_sha256(self.jar_bytes())

    @property
    def key(self) -> tuple[str, str]:
        return (self.category, self.filename)


class DefaultMods:
    """Standard mocked Forge mod entities used across E2E scenarios."""

    CREATE_V1 = ModFixture(CATEGORY_SERVER_CLIENT, "create", "1.0.0", "create-1.0.0.jar")
    CREATE_V1_PATCH = ModFixture(CATEGORY_SERVER_CLIENT, "create", "1.0.1", "create-1.0.0.jar")
    CREATE_V2 = ModFixture(CATEGORY_SERVER_CLIENT, "create", "2.0.0", "create-1.0.0.jar")
    CREATE_OUTDATED_LOCAL = ModFixture(CATEGORY_SERVER_CLIENT, "create", "0.5.0", "create-0.5.0.jar")

    JEI_V1 = ModFixture(CATEGORY_SERVER_CLIENT, "jei", "1.0.0", "jei-1.0.0.jar")
    TEMPORARY_V1 = ModFixture(CATEGORY_SERVER_CLIENT, "temporary_mod", "1.0.0", "temporary-1.0.0.jar")
    WAYSTONES_V1 = ModFixture(CATEGORY_SERVER_CLIENT, "waystones", "1.0.0", "waystones-1.0.0.jar")

    OCULUS_V1 = ModFixture(CATEGORY_CLIENT_ONLY, "oculus", "1.0.0", "oculus-1.0.0.jar")
    LUCKPERMS_V1 = ModFixture(CATEGORY_SERVER_ONLY, "luckperms", "1.0.0", "luckperms-1.0.0.jar")

    UNMANAGED_USER_FILENAME = "personal-minimap.jar"
    UNMANAGED_USER_PAYLOAD = b"unmanaged-user-jar-bytes"

    INITIAL_SERVER_SEED: tuple[ModFixture, ...] = (
        CREATE_V1,
        JEI_V1,
        OCULUS_V1,
        LUCKPERMS_V1,
    )


class InvalidInputs:
    """Invalid invite/URL/token fixture payloads used for negative tests."""

    CLI_INVALID_INVITE = "modsync://connect?url=ftp://invalid"
    GUI_INVALID_INVITE = "ftp://not-a-valid-modsync-invite"
    FALLBACK_SERVER_LINE = "http://127.0.0.1:8080\n"
    CLIENT_TOKEN = "wrong-client-token"


class BinaryPayloads:
    """Mocked binary payloads for updater and Inno Setup cleanup tests."""

    TAMPERED_RELEASE = b"tampered-binary-payload"
    VALID_RELEASE = b"updated-modsync-release-v99.0.0"
    STALE_OLD_BINARY = b"stale-old-binary"
    LEFTOVER_OLD_BINARY = b"leftover-old-binary"
    LEFTOVER_NEW_BINARY = b"leftover-new-binary"


@dataclass(frozen=True)
class PersistedConfigSnapshot:
    """Typed representation of ModSync's persisted config.json."""

    server_url: str
    mods_dir: Path
    client_token: str

    @classmethod
    def from_file(cls, cfg_path: Path) -> PersistedConfigSnapshot:
        raw = json.loads(cfg_path.read_text(encoding="utf-8"))
        return cls(
            server_url=str(raw[CFG_KEY_SERVER_URL]),
            mods_dir=Path(str(raw[CFG_KEY_MODS_DIR])),
            client_token=str(raw[CFG_KEY_CLIENT_TOKEN]),
        )
