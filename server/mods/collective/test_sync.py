#!/usr/bin/env python3
"""Unit and integration tests for mods/collective/sync.py."""

from __future__ import annotations

import contextlib
import copy
import importlib.util
import io
import json
import os
import shutil
import stat
import sys
import tempfile
import unittest
from pathlib import Path
from typing import TYPE_CHECKING, Any, cast

MOD_DIR = Path(__file__).resolve().parent
MODS_DIR = MOD_DIR.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

if TYPE_CHECKING:
    from _bridge import SyncModuleProtocol

SYNC_SCRIPT = MOD_DIR / "sync.py"
REL_PATH = "config/serilum/collective.json"


def load_sync_module() -> SyncModuleProtocol:
    """Load `mods/collective/sync.py` as an isolated module instance for testing."""
    spec = importlib.util.spec_from_file_location("collective_sync", SYNC_SCRIPT)
    if spec is None or spec.loader is None:
        raise RuntimeError(f"Could not load {SYNC_SCRIPT}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return cast("SyncModuleProtocol", module)


class CollectiveSyncTest(unittest.TestCase):
    """Verify Collective config validation, shared-dir isolation, secret guards, and placement."""

    def setUp(self) -> None:
        self.sync = load_sync_module()
        self.tmp_dir = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp_dir.name)
        self.configs_dir = self.root / "mods" / "collective" / "configs"
        self.data_dir = self.root / "data"

        shutil.copytree(MOD_DIR / "configs", self.configs_dir)
        self.data_dir.mkdir(parents=True, exist_ok=True)

        self.sync.CONFIGS_DIR = self.configs_dir
        self.sync.DATA_DIR = self.data_dir

    def tearDown(self) -> None:
        self.sync.CONFIGS_DIR = MOD_DIR / "configs"
        self.sync.DATA_DIR = MOD_DIR.parent.parent / "data"
        self.tmp_dir.cleanup()

    def _config_path(self) -> Path:
        return self.configs_dir / "config" / "serilum" / "collective.json"

    def _read_config(self) -> dict[str, Any]:
        return json.loads(self._config_path().read_text(encoding="utf-8"))

    def _write_config(self, payload: object) -> None:
        self._config_path().write_text(json.dumps(payload, indent=2), encoding="utf-8")

    def test_committed_configs_pass_validation(self) -> None:
        """Committed configs in mods/collective/configs/ must pass validate_configs()."""
        real_sync = load_sync_module()
        loaded = real_sync.validate_configs()
        self.assertEqual(set(loaded.keys()), {REL_PATH})

    def test_static_placement_permissions_idempotency_and_sibling_preservation(self) -> None:
        """Placement updates collective.json, preserves 0600, is idempotent, and leaves doubledoors.json untouched."""
        serilum_dir = self.data_dir / "config" / "serilum"
        serilum_dir.mkdir(parents=True, exist_ok=True)
        sibling_path = serilum_dir / "doubledoors.json"
        sibling_content = '{\n  "allowDoorsToOpenTogether": {\n    "value": true\n  }\n}\n'
        sibling_path.write_text(sibling_content, encoding="utf-8")

        target_path = serilum_dir / "collective.json"
        target_path.write_text('{"stale": true}', encoding="utf-8")
        os.chmod(target_path, 0o600)

        loaded = self.sync.validate_configs()
        buf1 = io.StringIO()
        with contextlib.redirect_stdout(buf1):
            changed, unchanged = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual((changed, unchanged), (1, 0))
        self.assertTrue(target_path.is_file())
        self.assertEqual(target_path.read_bytes(), loaded[REL_PATH])
        self.assertEqual(stat.S_IMODE(target_path.stat().st_mode), 0o600)
        self.assertEqual(sibling_path.read_text(encoding="utf-8"), sibling_content)

        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            changed_second, unchanged_second = self.sync.apply_configs(loaded, dry_run=False)
        self.assertEqual((changed_second, unchanged_second), (0, 1))
        self.assertEqual(sibling_path.read_text(encoding="utf-8"), sibling_content)

    def test_dry_run_leaves_data_dir_untouched(self) -> None:
        """CLI with --dry-run must leave DATA_DIR untouched when target is absent or stale."""
        buf1 = io.StringIO()
        with contextlib.redirect_stdout(buf1):
            rc1 = self.sync.main(["--dry-run"])
        self.assertEqual(rc1, 0)
        self.assertIn("DRY-RUN: 1 changed, 0 unchanged", buf1.getvalue())
        self.assertEqual(list(self.data_dir.rglob("*")), [])

        target_path = self.data_dir / "config" / "serilum" / "collective.json"
        target_path.parent.mkdir(parents=True, exist_ok=True)
        target_path.write_text('{"stale": true}', encoding="utf-8")
        buf2 = io.StringIO()
        with contextlib.redirect_stdout(buf2):
            rc2 = self.sync.main(["--dry-run"])
        self.assertEqual(rc2, 0)
        self.assertIn("DRY-RUN: 1 changed, 0 unchanged", buf2.getvalue())
        self.assertEqual(target_path.read_text(encoding="utf-8"), '{"stale": true}')

    def test_optional_comments_omitted_and_boundary_values_pass(self) -> None:
        """Optional '//' comments may be omitted and valid boundary/enum values must pass."""
        data = self._read_config()
        data.pop("//", None)
        for key, entry in data.items():
            if isinstance(entry, dict):
                entry.pop("//", None)
                data[key] = entry

        for delay, scale, lang, mode in (
            (0, 0, "en_us", "auto"),
            (3_600_000, 10, "de_de", "server"),
            (500, 5, "en", "client"),
            (1, 1, "en_7s", "auto"),
        ):
            data["findABlockCheckAroundEntitiesDelayMs"]["value"] = delay
            data["configScreenGuiScale"]["value"] = scale
            data["serverLanguage"]["value"] = lang
            data["itemNameTranslationMode"]["value"] = mode
            self._write_config(data)
            loaded = self.sync.validate_configs()
            self.assertIn(REL_PATH, loaded)

    def test_root_and_entry_structure_violations_raise_value_error(self) -> None:
        """Invalid JSON, non-object root/entries, missing/extra keys, and bad '//' comments raise ValueError."""
        base = self._read_config()

        # Invalid JSON syntax
        self._config_path().write_text("{broken json", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_json:
            self.sync.validate_configs()
        self.assertIn("invalid JSON", str(ctx_json.exception))

        # Root is a list instead of JSON object
        self._write_config([])
        with self.assertRaises(ValueError) as ctx_root_type:
            self.sync.validate_configs()
        self.assertIn("expected a mapping/table", str(ctx_root_type.exception))
        self.assertIn(
            "Collective JSON root must declare all 13 documented setting objects",
            str(ctx_root_type.exception),
        )

        # Missing required root key
        missing_root = copy.deepcopy(base)
        del missing_root["serverLanguage"]
        self._write_config(missing_root)
        with self.assertRaises(ValueError) as ctx_missing_key:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['serverLanguage']", str(ctx_missing_key.exception))
        self.assertIn("Serilum's config parser", str(ctx_missing_key.exception))

        # Unexpected extra root key
        extra_root = copy.deepcopy(base)
        extra_root["rogueSetting"] = {"value": True}
        self._write_config(extra_root)
        with self.assertRaises(ValueError) as ctx_extra_key:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['rogueSetting']", str(ctx_extra_key.exception))

        # Non-string root '//' comment
        bad_root_comment = copy.deepcopy(base)
        bad_root_comment["//"] = 123
        self._write_config(bad_root_comment)
        with self.assertRaises(ValueError) as ctx_root_comment:
            self.sync.validate_configs()
        self.assertIn("[root].'//' invariant violation", str(ctx_root_comment.exception))
        self.assertIn("Serilum's JSON comment metadata remains valid", str(ctx_root_comment.exception))

        # Entry is not a dict
        bad_entry_type = copy.deepcopy(base)
        bad_entry_type["enableUpdateChecker"] = True
        self._write_config(bad_entry_type)
        with self.assertRaises(ValueError) as ctx_entry_type:
            self.sync.validate_configs()
        self.assertIn("[enableUpdateChecker]: expected a mapping/table", str(ctx_entry_type.exception))
        self.assertIn("Each Collective setting entry must be a JSON object", str(ctx_entry_type.exception))

        # Entry missing 'value'
        missing_value = copy.deepcopy(base)
        del missing_value["enableUpdateChecker"]["value"]
        self._write_config(missing_value)
        with self.assertRaises(ValueError) as ctx_missing_val:
            self.sync.validate_configs()
        self.assertIn("missing required keys ['value']", str(ctx_missing_val.exception))

        # Entry unexpected extra key
        extra_entry_key = copy.deepcopy(base)
        extra_entry_key["enableUpdateChecker"]["default"] = True
        self._write_config(extra_entry_key)
        with self.assertRaises(ValueError) as ctx_extra_entry_key:
            self.sync.validate_configs()
        self.assertIn("unexpected keys ['default']", str(ctx_extra_entry_key.exception))

        # Non-string entry '//' comment
        bad_entry_comment = copy.deepcopy(base)
        bad_entry_comment["enableUpdateChecker"]["//"] = ["not", "a", "str"]
        self._write_config(bad_entry_comment)
        with self.assertRaises(ValueError) as ctx_entry_comment:
            self.sync.validate_configs()
        self.assertIn("[enableUpdateChecker].'//' invariant violation", str(ctx_entry_comment.exception))

    def test_value_type_range_and_enum_violations_raise_value_error(self) -> None:
        """All bool, strict int range, locale regex, string, and enum violations raise ValueError with rationale."""
        base = self._read_config()

        # Boolean keys reject non-booleans
        bool_keys = (
            "enableUpdateChecker",
            "transferItemsBetweenReplacedEntities",
            "enablePatronPets",
            "commandsAskForConfirmation",
            "downloadNonEnglishTranslations",
            "pushTranslationResourcePack",
            "requireTranslationResourcePack",
            "updateMinecraftWindowTitleInDevMode",
        )
        for key in bool_keys:
            for bad_bool in ("true", 1, 0, None):
                mutated = copy.deepcopy(base)
                mutated[key]["value"] = bad_bool
                self._write_config(mutated)
                with self.assertRaises(ValueError) as ctx_bool:
                    self.sync.validate_configs()
                msg = str(ctx_bool.exception)
                self.assertIn(f"[{key}].value invariant violation: must be a strict JSON boolean", msg)
                self.assertIn("Collective deserializes this flag", msg)

        # disabledSerilumMods rejects non-strings
        for bad_mods in (123, True, ["doubledoors"], None):
            mutated = copy.deepcopy(base)
            mutated["disabledSerilumMods"]["value"] = bad_mods
            self._write_config(mutated)
            with self.assertRaises(ValueError) as ctx_str:
                self.sync.validate_configs()
            msg = str(ctx_str.exception)
            self.assertIn("[disabledSerilumMods].value invariant violation: must be a string", msg)
            self.assertIn("disabled Serilum mod list string", msg)

        # Integer range keys reject bools, floats, strings, and out-of-range ints
        for key, bad_values in (
            ("findABlockCheckAroundEntitiesDelayMs", (True, False, -1, 3_600_001, 1.5, "30000", None)),
            ("configScreenGuiScale", (True, False, -1, 11, 2.5, "0", None)),
        ):
            for bad_int in bad_values:
                mutated = copy.deepcopy(base)
                mutated[key]["value"] = bad_int
                self._write_config(mutated)
                with self.assertRaises(ValueError) as ctx_int:
                    self.sync.validate_configs()
                msg = str(ctx_int.exception)
                self.assertIn(f"[{key}].value invariant violation: must be a strict integer in", msg)
                self.assertIn("remain safe and well-defined on server startup", msg)

        # serverLanguage rejects invalid locale strings and non-strings
        for bad_locale in ("", "EN_US", "en-us", "en__us", "_en_us", "en_us_", "en_us\n", 123, True):
            mutated = copy.deepcopy(base)
            mutated["serverLanguage"]["value"] = bad_locale
            self._write_config(mutated)
            with self.assertRaises(ValueError) as ctx_loc:
                self.sync.validate_configs()
            msg = str(ctx_loc.exception)
            self.assertIn("[serverLanguage].value invariant violation: must be a non-empty Minecraft locale code", msg)
            self.assertIn("resolves server-side Serilum mod translations deterministically", msg)

        # itemNameTranslationMode rejects invalid enum values
        for bad_mode in ("", "AUTO", "hybrid", 1, None):
            mutated = copy.deepcopy(base)
            mutated["itemNameTranslationMode"]["value"] = bad_mode
            self._write_config(mutated)
            with self.assertRaises(ValueError) as ctx_mode:
                self.sync.validate_configs()
            msg = str(ctx_mode.exception)
            self.assertIn("[itemNameTranslationMode].value invariant violation: must be one of", msg)
            self.assertIn("only supports 'auto', 'server', and 'client'", msg)

    def test_forbidden_files_dirs_suffixes_symlinks_and_secrets_rejected(self) -> None:
        """Forbidden sibling/runtime names, dirs, suffixes, symlinks, and secrets raise ValueError."""
        # Sibling Serilum config (both nested under config/serilum and at configs root)
        nested_sibling = self.configs_dir / "config" / "serilum" / "doubledoors.json"
        nested_sibling.write_text("{}", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_sibling:
            self.sync.validate_configs()
        self.assertIn(
            "Forbidden file/directory present in configs/: config/serilum/doubledoors.json",
            str(ctx_sibling.exception),
        )
        nested_sibling.unlink()

        # Live runtime translation state file and forbidden .txt suffix
        runtime_txt = self.configs_dir / "itemnametranslation.txt"
        runtime_txt.write_text("en_us", encoding="utf-8")
        with self.assertRaises(ValueError) as ctx_txt:
            self.sync.validate_configs()
        self.assertIn("Forbidden file/directory present in configs/: itemnametranslation.txt", str(ctx_txt.exception))
        self.assertIn(
            "Forbidden archive/runtime file present in configs/: itemnametranslation.txt",
            str(ctx_txt.exception),
        )
        runtime_txt.unlink()

        # Forbidden directories (cache, world, data)
        for dir_name in ("cache", "world", "data"):
            forbidden_dir = self.configs_dir / dir_name
            forbidden_dir.mkdir()
            with self.assertRaises(ValueError) as ctx_dir:
                self.sync.validate_configs()
            self.assertIn(f"Forbidden file/directory present in configs/: {dir_name}", str(ctx_dir.exception))
            forbidden_dir.rmdir()

        # Forbidden suffixes (.dat, .txt, .zip)
        for filename in ("state.dat", "notes.txt", "backup.zip"):
            bad_file = self.configs_dir / filename
            bad_file.write_bytes(b"dummy")
            with self.assertRaises(ValueError) as ctx_suffix:
                self.sync.validate_configs()
            self.assertIn(f"Forbidden archive/runtime file present in configs/: {filename}", str(ctx_suffix.exception))
            bad_file.unlink()

        # Symlink guard
        symlink_path = self.configs_dir / "link.json"
        symlink_path.symlink_to(self._config_path())
        with self.assertRaises(ValueError) as ctx_sym:
            self.sync.validate_configs()
        self.assertIn("Symlinks are forbidden in configs/: link.json", str(ctx_sym.exception))
        symlink_path.unlink()

        # Secret guard: secret pattern in comment
        base = self._read_config()
        with_webhook = copy.deepcopy(base)
        with_webhook["//"] = "https://discord.com/api/webhooks/123456789/abcdef_token"
        self._write_config(with_webhook)
        with self.assertRaises(ValueError) as ctx_webhook:
            self.sync.validate_configs()
        self.assertIn("Discord Webhook URL", str(ctx_webhook.exception))

        # Secret guard: credential key in JSON
        with_secret_key = copy.deepcopy(base)
        with_secret_key["password"] = "supersecret"
        self._write_config(with_secret_key)
        with self.assertRaises(ValueError) as ctx_secret_key:
            self.sync.validate_configs()
        self.assertIn("non-empty secret key 'password'", str(ctx_secret_key.exception))


if __name__ == "__main__":
    unittest.main()
