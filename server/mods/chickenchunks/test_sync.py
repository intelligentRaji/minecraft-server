#!/usr/bin/env python3
"""Unit and integration tests for mods/chickenchunks/sync.py."""

from __future__ import annotations

import contextlib
import importlib.util
import io
import os
import tempfile
import unittest
from pathlib import Path
from typing import Protocol, cast

MOD_DIR = Path(__file__).resolve().parent
SYNC_SCRIPT = MOD_DIR / "sync.py"

SAMPLE_CFG = (
    "# If Players with OP permissions bypass chunk loading restrictions.\n"
    'B:"opsBypassRestrictions"=false\n\n'
    "# If Players with OP permissions can manage other users ChunkLoaders\n"
    'B:"opsAccessAllLoaders"=true\n\n'
    "# If chunks should stay loaded when a ChunkLoader's owner is offline.\n"
    'B:"allowOffline"=false\n\n'
    "# How long in minutes ChickenChunks should wait after a Player logs out to unload their chunks. "
    "Only effective when allowOffline=false\n"
    'I:"offlineTimeout"=0\n\n'
    "# The number of chunks each player is allowed to load in total.\n"
    'I:"totalAllowedChunks"=25\n\n'
    "# The number of chunks each ChunkLoader is allowed to load in total.\n"
    'I:"chunksPerLoader"=25\n'
)


class ChickenChunksSyncProtocol(Protocol):
    """Typed interface for the dynamically loaded `mods/chickenchunks/sync.py` module."""

    CONFIGS_DIR: Path
    DATA_DIR: Path
    TARGET_DIR: Path
    STATIC_FILES: tuple[str, ...]

    def validate_configs(self) -> dict[str, str]: ...

    def apply_configs(self, loaded_texts: dict[str, str], dry_run: bool) -> tuple[int, int]: ...

    def main(self, argv: list[str] | None = None) -> int: ...


def load_sync_module() -> ChickenChunksSyncProtocol:
    """Load `mods/chickenchunks/sync.py` as an isolated module instance for testing."""
    spec = importlib.util.spec_from_file_location("chickenchunks_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("ChickenChunksSyncProtocol", module)


class ChickenChunksSyncTest(unittest.TestCase):
    """Verify ChickenChunks validation, runtime state isolation, block merges, and guards."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "chickenchunks" / "configs"
        self.data_dir = self.root / "data"
        self.target_dir = self.data_dir / "config"

        self.configs_dir.mkdir(parents=True, exist_ok=True)
        (self.configs_dir / "ChickenChunks.cfg").write_text(SAMPLE_CFG, encoding="utf-8")
        self.target_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir
        self.sync.TARGET_DIR = self.target_dir

    def tearDown(self) -> None:
        self.tmp_dir.cleanup()

    def test_committed_repo_configs_are_valid(self) -> None:
        """The real committed mods/chickenchunks/configs/ directory must pass all pre-flight checks."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(list(loaded.keys()), ["ChickenChunks.cfg"])

    def test_initial_placement_permissions_and_idempotency(self) -> None:
        """Initial run creates ChickenChunks.cfg with default block; second run is idempotent and preserves mode."""
        target_cfg = self.target_dir / "ChickenChunks.cfg"
        self.assertFalse(target_cfg.exists())

        buf1 = io.StringIO()
        with contextlib.redirect_stdout(buf1):
            rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        self.assertIn("APPLIED: 1 changed, 0 unchanged", buf1.getvalue())
        self.assertTrue(target_cfg.is_file())

        placed = target_cfg.read_text(encoding="utf-8")
        self.assertIn('B:"opsBypassRestrictions"=false', placed)
        self.assertIn('I:"chunksPerLoader"=25', placed)
        self.assertIn(
            '# Specifies restrictions for each player, Use /chickenchunks instead.\n"playerRestrictions" {\n}',
            placed,
        )

        # Second run with no edits must report 0 changed, 1 unchanged
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("APPLIED: 0 changed, 1 unchanged", buf2.getvalue())

        # Restrict permissions on target and edit source static key; placement must preserve 0o600 mode
        os.chmod(target_cfg, 0o600)
        src_cfg = self.configs_dir / "ChickenChunks.cfg"
        src_cfg.write_text(
            src_cfg.read_text(encoding="utf-8").replace(
                'I:"chunksPerLoader"=25',
                'I:"chunksPerLoader"=9',
            ),
            encoding="utf-8",
        )

        rc3 = self.sync.main([])
        self.assertEqual(rc3, 0)
        self.assertEqual(target_cfg.stat().st_mode & 0o777, 0o600)
        self.assertIn('I:"chunksPerLoader"=9', target_cfg.read_text(encoding="utf-8"))

    def test_block_merge_preserves_nested_live_player_restrictions_and_idempotency(self) -> None:
        """Block-level merge updates static settings while keeping nested live UUID restrictions intact."""
        live_cfg = (
            "# Old static settings\n"
            'B:"opsBypassRestrictions"=true\n\n'
            'B:"opsAccessAllLoaders"=false\n\n'
            'B:"allowOffline"=false\n\n'
            'I:"offlineTimeout"=30\n\n'
            'I:"totalAllowedChunks"=999\n\n'
            'I:"chunksPerLoader"=99\n\n'
            "# Specifies restrictions for each player, Use /chickenchunks instead.\n"
            '"playerRestrictions" {\n'
            '\t"419a8875-fda5-3754-b761-2b32ce8c49c0" {\n'
            '\t\tI:"chunksPerLoader"=64\n'
            '\t\tI:"totalAllowedChunks"=128\n'
            "\t\t# Brace { in comment should not break depth tracking\n"
            '\t\tS:"note"="}"\n'
            "\t}\n"
            '\t"7e6b6b20-1234-4abc-9def-001122334455" {\n'
            '\t\tB:"allowOffline"=false\n'
            "\t}\n"
            "}\n"
        )
        target_cfg = self.target_dir / "ChickenChunks.cfg"
        target_cfg.write_text(live_cfg, encoding="utf-8")

        rc1 = self.sync.main([])
        self.assertEqual(rc1, 0)
        merged = target_cfg.read_text(encoding="utf-8")

        # Static keys updated from configs/ChickenChunks.cfg
        self.assertIn('B:"opsBypassRestrictions"=false', merged)
        self.assertIn('B:"opsAccessAllLoaders"=true', merged)
        self.assertIn('B:"allowOffline"=false', merged)
        self.assertIn('I:"offlineTimeout"=0', merged)
        self.assertIn('I:"totalAllowedChunks"=25', merged)
        self.assertIn('I:"chunksPerLoader"=25', merged)

        # Nested live player UUID restrictions preserved verbatim
        self.assertIn('"419a8875-fda5-3754-b761-2b32ce8c49c0" {', merged)
        self.assertIn('I:"chunksPerLoader"=64', merged)
        self.assertIn('I:"totalAllowedChunks"=128', merged)
        self.assertIn('"7e6b6b20-1234-4abc-9def-001122334455" {', merged)
        self.assertIn('\t\tB:"allowOffline"=false', merged)

        # Subsequent sync must be strictly idempotent
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = self.sync.main([])
        self.assertEqual(rc2, 0)
        self.assertIn("APPLIED: 0 changed, 1 unchanged", buf2.getvalue())

    def test_block_merge_handles_missing_comment_or_missing_block_and_rejects_unclosed_target(self) -> None:
        """Merge emits default comment when absent, defaults missing block, and fails on unclosed target block."""
        target_cfg = self.target_dir / "ChickenChunks.cfg"

        # Case 1: Target has "playerRestrictions" without preceding comment
        target_cfg.write_text(
            'I:"chunksPerLoader"=10\n\n"playerRestrictions" {\n\t"uuid-1" {\n\t\tI:"chunksPerLoader"=5\n\t}\n}\n',
            encoding="utf-8",
        )
        self.assertEqual(self.sync.main([]), 0)
        merged = target_cfg.read_text(encoding="utf-8")
        self.assertIn("# Specifies restrictions for each player, Use /chickenchunks instead.", merged)
        self.assertIn('"uuid-1" {', merged)

        # Case 2: Target exists without "playerRestrictions" block at all
        target_cfg.write_text('I:"chunksPerLoader"=10\n', encoding="utf-8")
        self.assertEqual(self.sync.main([]), 0)
        self.assertIn('"playerRestrictions" {\n}', target_cfg.read_text(encoding="utf-8"))

        # Case 3: Target has malformed/unclosed "playerRestrictions" block
        target_cfg.write_text('"playerRestrictions" {\n\t"uuid-1" {\n', encoding="utf-8")
        loaded = self.sync.validate_configs()
        with self.assertRaises(ValueError) as ctx:
            self.sync.apply_configs(loaded, dry_run=False)
        self.assertIn("unclosed 'playerRestrictions' block", str(ctx.exception))

    def test_dry_run_does_not_write_or_modify_target_dir(self) -> None:
        """--dry-run leaves TARGET_DIR untouched both when missing and when target already exists."""
        # Missing target
        buf1 = io.StringIO()
        with contextlib.redirect_stdout(buf1):
            rc1 = self.sync.main(["--dry-run"])
        self.assertEqual(rc1, 0)
        self.assertIn("DRY-RUN: 1 changed, 0 unchanged", buf1.getvalue())
        self.assertEqual(list(self.target_dir.iterdir()), [])

        # Existing outdated target
        target_cfg = self.target_dir / "ChickenChunks.cfg"
        original_content = 'I:"chunksPerLoader"=123\n"playerRestrictions" {\n}\n'
        target_cfg.write_text(original_content, encoding="utf-8")

        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = self.sync.main(["--dry-run"])
        self.assertEqual(rc2, 0)
        self.assertIn("DRY-RUN: 1 changed, 0 unchanged", buf2.getvalue())
        self.assertEqual(target_cfg.read_text(encoding="utf-8"), original_content)

    def test_player_restrictions_block_or_key_rejected_in_repo_configs(self) -> None:
        """Committing 'playerRestrictions' into configs/ChickenChunks.cfg must fail with runtime isolation rationale."""
        cfg_path = self.configs_dir / "ChickenChunks.cfg"
        base = cfg_path.read_text(encoding="utf-8")

        for snippet in (
            '\n"playerRestrictions" {\n}\n',
            '\n"playerRestrictions" {\n\t"uuid-1" {\n\t\tI:"chunksPerLoader"=10\n\t}\n}\n',
            '\nS:"playerRestrictions"="bad"\n',
        ):
            cfg_path.write_text(base + snippet, encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn("state isolation violation", str(ctx.exception))
            self.assertIn("playerRestrictions", str(ctx.exception))
            self.assertIn("block-level merge", str(ctx.exception))

    def test_missing_and_unexpected_files_rejected(self) -> None:
        """configs/ must contain exactly ChickenChunks.cfg."""
        cfg_path = self.configs_dir / "ChickenChunks.cfg"
        (self.configs_dir / "extra.cfg").write_text("", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_extra:
            self.sync.validate_configs()
        self.assertIn("Unexpected files in configs/: extra.cfg", str(ctx_extra.exception))
        (self.configs_dir / "extra.cfg").unlink()

        cfg_path.unlink()
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("Missing expected config files in configs/: ChickenChunks.cfg", str(ctx_missing.exception))

    def test_schema_type_and_value_invariants_rejected(self) -> None:
        """Missing keys, unexpected keys/blocks, wrong prefixes, bad booleans, and negative ints fail with rationale."""
        cfg_path = self.configs_dir / "ChickenChunks.cfg"
        base = cfg_path.read_text(encoding="utf-8")

        # Missing required key
        cfg_path.write_text(
            base.replace('I:"chunksPerLoader"=25\n', ""),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_missing:
            self.sync.validate_configs()
        self.assertIn("missing required static administrator key 'chunksPerLoader'", str(ctx_missing.exception))

        # Unexpected key
        cfg_path.write_text(base + '\nB:"unexpectedFlag"=true\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_unexpected_key:
            self.sync.validate_configs()
        self.assertIn("unexpected key 'unexpectedFlag'", str(ctx_unexpected_key.exception))

        # Unexpected block
        cfg_path.write_text(base + '\n"customSection" {\n}\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_unexpected_block:
            self.sync.validate_configs()
        self.assertIn("unexpected block 'customSection'", str(ctx_unexpected_block.exception))

        # Duplicate key
        cfg_path.write_text(base + '\nB:"allowOffline"=false\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_dup:
            self.sync.validate_configs()
        self.assertIn("duplicate key 'allowOffline'", str(ctx_dup.exception))

        # Wrong type prefix
        cfg_path.write_text(
            base.replace('B:"opsBypassRestrictions"=false', 'S:"opsBypassRestrictions"=false'),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_prefix:
            self.sync.validate_configs()
        self.assertIn("must use CodeChickenLib type prefix 'B:'", str(ctx_prefix.exception))

        # Invalid boolean value
        cfg_path.write_text(
            base.replace('B:"allowOffline"=false', 'B:"allowOffline"=yes'),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_bool:
            self.sync.validate_configs()
        self.assertIn("boolean key 'allowOffline' must be 'true' or 'false'", str(ctx_bool.exception))

        # Negative integer and non-integer values
        for bad_val in ("-1", "12.5", "abc"):
            cfg_path.write_text(
                base.replace('I:"offlineTimeout"=0', f'I:"offlineTimeout"={bad_val}'),
                encoding="utf-8",
            )
            with self.assertRaises(ValueError) as ctx_int:
                self.sync.validate_configs()
            self.assertIn("non-negative integer >= 0", str(ctx_int.exception))

        # Unclosed block / syntax error
        cfg_path.write_text(base + '\n"broken" {\n', encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_unclosed:
            self.sync.validate_configs()
        self.assertIn("unclosed block 'broken'", str(ctx_unclosed.exception))

    def test_server_policy_guardrails_rejected_and_boundaries_accepted(self) -> None:
        """Every developer/server policy setting must enforce its guardrail bounds and cross-key relation."""
        cfg_path = self.configs_dir / "ChickenChunks.cfg"
        base = cfg_path.read_text(encoding="utf-8")

        cases = [
            (
                'B:"opsBypassRestrictions"=false',
                'B:"opsBypassRestrictions"=true',
                "opsBypassRestrictions must be 'false'",
            ),
            (
                'B:"allowOffline"=false',
                'B:"allowOffline"=true',
                "allowOffline must be 'false'",
            ),
            (
                'I:"offlineTimeout"=0',
                'I:"offlineTimeout"=61',
                "offlineTimeout must be in 0..60 minutes",
            ),
            (
                'I:"totalAllowedChunks"=25',
                'I:"totalAllowedChunks"=0',
                "totalAllowedChunks must be in 1..25",
            ),
            (
                'I:"totalAllowedChunks"=25',
                'I:"totalAllowedChunks"=26',
                "totalAllowedChunks must be in 1..25",
            ),
            (
                'I:"chunksPerLoader"=25',
                'I:"chunksPerLoader"=0',
                "chunksPerLoader must be in 1..25",
            ),
            (
                'I:"chunksPerLoader"=25',
                'I:"chunksPerLoader"=26',
                "chunksPerLoader must be in 1..25",
            ),
        ]
        for old, new, expected_msg in cases:
            cfg_path.write_text(base.replace(old, new), encoding="utf-8")
            with self.assertRaises(ValueError) as ctx:
                self.sync.validate_configs()
            self.assertIn(expected_msg, str(ctx.exception))

        # chunksPerLoader > totalAllowedChunks rejected
        cfg_path.write_text(
            base.replace('I:"totalAllowedChunks"=25', 'I:"totalAllowedChunks"=10').replace(
                'I:"chunksPerLoader"=25', 'I:"chunksPerLoader"=20'
            ),
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_rel:
            self.sync.validate_configs()
        self.assertIn("chunksPerLoader (20) must not exceed totalAllowedChunks (10)", str(ctx_rel.exception))

        # Valid boundaries pass
        cfg_path.write_text(
            base.replace('B:"opsAccessAllLoaders"=true', 'B:"opsAccessAllLoaders"=false')
            .replace('I:"offlineTimeout"=0', 'I:"offlineTimeout"=60')
            .replace('I:"totalAllowedChunks"=25', 'I:"totalAllowedChunks"=1')
            .replace('I:"chunksPerLoader"=25', 'I:"chunksPerLoader"=1'),
            encoding="utf-8",
        )
        loaded = self.sync.validate_configs()
        self.assertIn("ChickenChunks.cfg", loaded)

    def test_forbidden_files_suffixes_symlinks_and_secrets_rejected(self) -> None:
        """Forbidden runtime files/dirs, forbidden suffixes, symlinks, and secrets must fail validation."""
        # Forbidden name (loginTimes.dat / world dir)
        (self.configs_dir / "loginTimes.dat").write_bytes(b"\x00\x01")
        with self.assertRaises(ValueError) as ctx_name:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory present in configs/: loginTimes.dat", str(ctx_name.exception))
        (self.configs_dir / "loginTimes.dat").unlink()

        world_dir = self.configs_dir / "world"
        world_dir.mkdir()
        with self.assertRaises(ValueError) as ctx_dir:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory present in configs/: world", str(ctx_dir.exception))
        world_dir.rmdir()

        # Forbidden suffix (.dat, .db)
        (self.configs_dir / "chunkloader_state.dat").write_bytes(b"binary")
        with self.assertRaises(ValueError) as ctx_dat:
            self.sync.validate_configs()
        self.assertIn(
            "Forbidden runtime/archive file present in configs/: chunkloader_state.dat",
            str(ctx_dat.exception),
        )
        (self.configs_dir / "chunkloader_state.dat").unlink()

        (self.configs_dir / "state.db").write_bytes(b"sqlite")
        with self.assertRaises(ValueError) as ctx_db:
            self.sync.validate_configs()
        self.assertIn("Forbidden runtime/archive file present in configs/: state.db", str(ctx_db.exception))
        (self.configs_dir / "state.db").unlink()

        # Symlink guard
        symlink_path = self.configs_dir / "link.cfg"
        symlink_path.symlink_to(self.configs_dir / "ChickenChunks.cfg")
        with self.assertRaises(ValueError) as ctx_sym:
            self.sync.validate_configs()
        self.assertIn("Symlinks are forbidden in configs/: link.cfg", str(ctx_sym.exception))
        symlink_path.unlink()

        # Secret scan guard
        cfg_path = self.configs_dir / "ChickenChunks.cfg"
        cfg_path.write_text(
            cfg_path.read_text(encoding="utf-8")
            + "\n# https://discord.com/api/webhooks/123456789/abcdef-token\n",
            encoding="utf-8",
        )
        with self.assertRaises(ValueError) as ctx_secret:
            self.sync.validate_configs()
        self.assertIn("Discord Webhook URL", str(ctx_secret.exception))


if __name__ == "__main__":
    unittest.main()
