"""Unit tests for server/sync_mods.py."""

from __future__ import annotations

import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

import sync_mods


class SyncModsTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.modpack_dir = self.root / "modpack"
        self.data_mods_dir = self.root / "data" / "mods"
        for cat in ("server-client", "server-only", "client-only"):
            (self.modpack_dir / cat).mkdir(parents=True)
        self.data_mods_dir.mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_syncs_server_categories_ignores_client_only_and_prunes_stale(self) -> None:
        (self.modpack_dir / "server-client" / "create.jar").write_bytes(b"create-v1")
        (self.modpack_dir / "server-only" / "spark.jar").write_bytes(b"spark-v1")
        (self.modpack_dir / "client-only" / "oculus.jar").write_bytes(b"oculus-v1")
        (self.data_mods_dir / "old.jar").write_bytes(b"stale")

        updated, removed, unchanged = sync_mods.sync_server_mods(self.modpack_dir, self.data_mods_dir)
        self.assertEqual((updated, removed, unchanged), (2, 1, 0))
        self.assertEqual(sorted(p.name for p in self.data_mods_dir.iterdir()), ["create.jar", "spark.jar"])

        # Second run is idempotent
        self.assertEqual(sync_mods.sync_server_mods(self.modpack_dir, self.data_mods_dir), (0, 0, 2))

        # Dry run leaves files untouched
        (self.modpack_dir / "server-client" / "jade.jar").write_bytes(b"jade")
        self.assertEqual(
            sync_mods.sync_server_mods(self.modpack_dir, self.data_mods_dir, dry_run=True),
            (1, 0, 2),
        )
        self.assertFalse((self.data_mods_dir / "jade.jar").exists())

    def test_main_aborts_before_touching_data_mods_when_api_unhealthy(self) -> None:
        (self.modpack_dir / "server-client" / "new.jar").write_bytes(b"new-mod")
        (self.data_mods_dir / "existing.jar").write_bytes(b"old-mod")

        with (
            patch.object(sync_mods, "MODPACK_DIR", self.modpack_dir),
            patch.object(sync_mods, "DATA_MODS_DIR", self.data_mods_dir),
            patch.object(sync_mods, "_check_modsync_health", side_effect=OSError("connection refused")),
        ):
            rc = sync_mods.main(["--modsync-url", "http://modsync-api:8080"])

        self.assertEqual(rc, 1)
        self.assertEqual([p.name for p in self.data_mods_dir.iterdir()], ["existing.jar"])

    def test_main_syncs_and_notifies_api_when_healthy(self) -> None:
        (self.modpack_dir / "server-client" / "new.jar").write_bytes(b"new-mod")

        with (
            patch.object(sync_mods, "MODPACK_DIR", self.modpack_dir),
            patch.object(sync_mods, "DATA_MODS_DIR", self.data_mods_dir),
            patch.dict("os.environ", {"MODSYNC_ADMIN_TOKEN": "admin-secret"}),
            patch.object(sync_mods, "_check_modsync_health") as mock_health,
            patch.object(sync_mods, "_trigger_modsync_reload", return_value={"version": "abc", "notified_clients": 2}) as mock_reload,
        ):
            rc = sync_mods.main(["--modsync-url", "http://modsync-api:8080"])

        self.assertEqual(rc, 0)
        mock_health.assert_called_once_with("http://modsync-api:8080")
        mock_reload.assert_called_once_with("http://modsync-api:8080", "admin-secret")
        self.assertTrue((self.data_mods_dir / "new.jar").is_file())


if __name__ == "__main__":
    unittest.main()
