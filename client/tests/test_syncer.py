"""Unit tests for ModSync client config, SHA-256 verification, staging, and pruning."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
import sys

CLIENT_SRC = Path(__file__).resolve().parents[1] / "src"
if str(CLIENT_SRC) not in sys.path:
    sys.path.insert(0, str(CLIENT_SRC))

from modsync_client.config import AppConfig, build_ws_url, load_config, save_config  # noqa: E402
from modsync_client.syncer import ModSyncer, SyncStatus, parse_manifest  # noqa: E402


class FakeTransport:
    def __init__(self, manifest_payload: dict, files: dict[str, bytes]) -> None:
        self.manifest_payload = manifest_payload
        self.files = files
        self.downloads: list[str] = []

    def get_json(self, _url: str) -> dict:
        return self.manifest_payload

    def download_to(self, url: str, dest_path: Path) -> None:
        self.downloads.append(url)
        dest_path.parent.mkdir(parents=True, exist_ok=True)
        for key, payload in self.files.items():
            if url.endswith(key):
                dest_path.write_bytes(payload)
                return
        raise FileNotFoundError(f"Unexpected download URL: {url}")


def _manifest_for(files: dict[str, bytes], version: str = "v1") -> dict:
    mods = []
    for name, payload in sorted(files.items()):
        mods.append(
            {
                "filename": name,
                "category": "server-client",
                "sha256": hashlib.sha256(payload).hexdigest(),
                "size": len(payload),
                "url": f"/api/mods/server-client/{name}",
            }
        )
    return {"version": version, "mods": mods}


class ConfigTests(unittest.TestCase):
    def test_build_ws_url_and_persistence(self) -> None:
        self.assertEqual(build_ws_url("https://mods.example.com/"), "wss://mods.example.com/ws")
        self.assertEqual(
            build_ws_url("http://127.0.0.1:8080", "tok123"),
            "ws://127.0.0.1:8080/ws?token=tok123",
        )
        with self.assertRaises(ValueError):
            build_ws_url("ftp://invalid")

        with tempfile.TemporaryDirectory() as tmp:
            cfg_path = Path(tmp) / "config.json"
            cfg = AppConfig(server_url="https://mods.example.com", mods_dir="/tmp/mods")
            save_config(cfg, cfg_path)
            loaded = load_config(cfg_path)
            self.assertEqual(loaded, cfg)


class SyncerTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.mods_dir = self.root / "mods"
        self.staging_dir = self.root / "staging"
        self.mods_dir.mkdir()

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_initial_sync_update_and_prune(self) -> None:
        (self.mods_dir / "old-mod.jar").write_bytes(b"stale")
        remote_files = {
            "create.jar": b"create-v1",
            "jade.jar": b"jade-v1",
        }
        transport = FakeTransport(_manifest_for(remote_files, "v1"), remote_files)
        syncer = ModSyncer(
            server_url="https://mods.example.com",
            mods_dir=self.mods_dir,
            staging_dir=self.staging_dir,
            transport=transport,
            mc_running_check=lambda: False,
        )

        res = syncer.sync_once()
        self.assertEqual(res.status, SyncStatus.SYNCED)
        self.assertEqual(res.added, ("create.jar", "jade.jar"))
        self.assertEqual(res.removed, ("old-mod.jar",))
        self.assertFalse((self.mods_dir / "old-mod.jar").exists())
        self.assertEqual((self.mods_dir / "create.jar").read_bytes(), b"create-v1")

        # Second sync is a no-op with 0 downloads
        transport.downloads.clear()
        res2 = syncer.sync_once()
        self.assertEqual(res2.status, SyncStatus.SYNCED)
        self.assertEqual(transport.downloads, [])

    def test_stages_when_minecraft_running_then_applies_on_exit(self) -> None:
        (self.mods_dir / "create.jar").write_bytes(b"create-v1")
        remote_files = {"create.jar": b"create-v2", "oculus.jar": b"oculus-v1"}
        transport = FakeTransport(_manifest_for(remote_files, "v2"), remote_files)

        mc_running = True
        syncer = ModSyncer(
            server_url="https://mods.example.com",
            mods_dir=self.mods_dir,
            staging_dir=self.staging_dir,
            transport=transport,
            mc_running_check=lambda: mc_running,
        )

        res = syncer.sync_once()
        self.assertEqual(res.status, SyncStatus.STAGED_WAITING_MC)
        # Live mods_dir must remain untouched while Minecraft is open
        self.assertEqual((self.mods_dir / "create.jar").read_bytes(), b"create-v1")
        self.assertFalse((self.mods_dir / "oculus.jar").exists())
        self.assertIsNone(syncer.try_apply_staged())

        # Once Minecraft exits, try_apply_staged moves staged files atomically
        mc_running = False
        applied = syncer.try_apply_staged()
        self.assertIsNotNone(applied)
        assert applied is not None
        self.assertEqual(applied.status, SyncStatus.SYNCED)
        self.assertEqual((self.mods_dir / "create.jar").read_bytes(), b"create-v2")
        self.assertEqual((self.mods_dir / "oculus.jar").read_bytes(), b"oculus-v1")

    def test_rejects_sha256_mismatch_and_unsafe_filenames(self) -> None:
        bad_manifest = {
            "version": "bad",
            "mods": [
                {
                    "filename": "create.jar",
                    "category": "server-client",
                    "sha256": "0" * 64,
                    "size": 9,
                    "url": "/api/mods/server-client/create.jar",
                }
            ],
        }
        transport = FakeTransport(bad_manifest, {"create.jar": b"tampered!"})
        syncer = ModSyncer(
            server_url="https://mods.example.com",
            mods_dir=self.mods_dir,
            staging_dir=self.staging_dir,
            transport=transport,
            mc_running_check=lambda: False,
        )
        with self.assertRaises(ValueError):
            syncer.sync_once()
        self.assertFalse((self.mods_dir / "create.jar").exists())

        with self.assertRaises(ValueError):
            parse_manifest(
                {
                    "version": "evil",
                    "mods": [
                        {
                            "filename": "../evil.jar",
                            "category": "server-client",
                            "sha256": "a" * 64,
                            "size": 1,
                            "url": "/api/mods/server-client/evil.jar",
                        }
                    ],
                }
            )


if __name__ == "__main__":
    unittest.main()
