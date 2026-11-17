"""Unit tests for `mods/_bridge/schema.py`."""

from __future__ import annotations

import sys
import unittest
from pathlib import Path

MODS_DIR = Path(__file__).resolve().parent.parent.parent
if str(MODS_DIR) not in sys.path:
    sys.path.insert(0, str(MODS_DIR))

from _bridge.schema import check_table_keys, is_finite_number, is_strict_int  # noqa: E402


class BridgeSchemaTest(unittest.TestCase):
    def test_is_strict_int_rejects_booleans(self) -> None:
        self.assertTrue(is_strict_int(0))
        self.assertTrue(is_strict_int(42))
        self.assertFalse(is_strict_int(True))
        self.assertFalse(is_strict_int(False))
        self.assertFalse(is_strict_int("42"))

    def test_is_finite_number_and_check_table_keys(self) -> None:
        self.assertTrue(is_finite_number(0))
        self.assertTrue(is_finite_number(1.5))
        self.assertFalse(is_finite_number(True))
        self.assertFalse(is_finite_number(float("nan")))
        self.assertFalse(is_finite_number(float("inf")))
        self.assertFalse(is_finite_number("1.5"))

        self.assertEqual(
            check_table_keys("not-a-dict", "section", ("a",)),
            ["section: expected a mapping/table (got str)"],
        )
        errors = check_table_keys(
            {"a": 1, "extra": 2},
            "section",
            required_keys=("a", "b"),
            optional_keys=("c",),
        )
        self.assertEqual(len(errors), 2)
        self.assertTrue(any("missing required keys ['b']" in e for e in errors))
        self.assertTrue(any("unexpected keys ['extra']" in e for e in errors))
        self.assertEqual(
            check_table_keys({"a": 1, "b": 2, "c": 3}, "section", ("a", "b"), ("c",)),
            [],
        )


if __name__ == "__main__":
    unittest.main()
