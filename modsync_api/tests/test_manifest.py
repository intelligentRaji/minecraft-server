"""Unit tests for deterministic modpack manifest generation and path validation."""

from __future__ import annotations

import hashlib
import tempfile
import unittest
from pathlib import Path
import sys

API_ROOT = Path(__file__).resolve().parents[1]
if str(API_ROOT) not in sys.path:
    sys.path.insert(0, str(API_ROOT))

from app.manifest import ManifestStore, validate_jar_request  # noqa: E402


class ManifestUnitTests(unittest.TestCase):
    def setUp(self) -> None:
        self.tmp = tempfile.TemporaryDirectory()
        self.modpack_dir = Path(self.tmp.name) / "modpack"
        (self.modpack_dir / "server-client").mkdir(parents=True)
        (self.modpack_dir / "client-only").mkdir(parents=True)
        (self.modpack_dir / "server-only").mkdir(parents=True)

    def tearDown(self) -> None:
        self.tmp.cleanup()

    def test_ignores_server_only_and_hashes_client_mods(self) -> None:
        sc_jar = self.modpack_dir / "server-client" / "create-1.20.1.jar"
        co_jar = self.modpack_dir / "client-only" / "embeddium-0.3.jar"
        so_jar = self.modpack_dir / "server-only" / "chunky-1.3.jar"
        sc_jar.write_bytes(b"create-bytes")
        co_jar.write_bytes(b"embeddium-bytes")
        so_jar.write_bytes(b"chunky-bytes")

        store = ManifestStore(self.modpack_dir)
        manifest, changed = store.refresh()
        self.assertFalse(changed)  # initial load has no previous version
        self.assertEqual([m.filename for m in manifest.mods], ["create-1.20.1.jar", "embeddium-0.3.jar"])

        expected_sha = hashlib.sha256(b"create-bytes").hexdigest()
        self.assertEqual(manifest.mods[0].sha256, expected_sha)
        self.assertEqual(manifest.mods[0].url, "/api/mods/server-client/create-1.20.1.jar")

        # Refresh again without changes -> changed=False, identical version
        manifest2, changed2 = store.refresh()
        self.assertFalse(changed2)
        self.assertEqual(manifest.version, manifest2.version)

        # Add a new client-only jar -> changed=True, version changes
        (self.modpack_dir / "client-only" / "appleskin.jar").write_bytes(b"apple-bytes")
        manifest3, changed3 = store.refresh()
        self.assertTrue(changed3)
        self.assertNotEqual(manifest.version, manifest3.version)
        self.assertEqual(len(manifest3.mods), 3)

    def test_validate_jar_request_blocks_server_only_and_traversal(self) -> None:
        (self.modpack_dir / "server-only" / "secret-admin.jar").write_bytes(b"secret")
        (self.modpack_dir / "server-client" / "ok-mod+1.20.1.jar").write_bytes(b"ok")

        self.assertIsNone(validate_jar_request(self.modpack_dir, "server-only", "secret-admin.jar"))
        self.assertIsNone(validate_jar_request(self.modpack_dir, "server-client", "../server-only/secret-admin.jar"))
        self.assertIsNone(validate_jar_request(self.modpack_dir, "server-client", "not-a-jar.txt"))
        resolved = validate_jar_request(self.modpack_dir, "server-client", "ok-mod+1.20.1.jar")
        self.assertIsNotNone(resolved)
        assert resolved is not None
        self.assertEqual(resolved.name, "ok-mod+1.20.1.jar")


if __name__ == "__main__":
    unittest.main()
