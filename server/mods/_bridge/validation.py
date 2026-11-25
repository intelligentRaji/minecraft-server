"""Pre-flight validation pipeline for static mod configuration directories."""

from __future__ import annotations

import configparser
import json
import tomllib
from collections.abc import Callable, Iterable, Mapping
from pathlib import Path
from typing import Any

from .files import (
    DEFAULT_FORBIDDEN_SUFFIXES,
    check_forbidden_entries,
    collect_config_files,
)
from .secrets import scan_mapping_for_secrets, scan_text_for_secrets


def _parse_static_config(rel: str, raw_text: str) -> tuple[Any, str | None]:
    """Parse `.toml`, `.json`, or `.ini` static config text; return `(parsed, error)`."""
    lower = rel.lower()
    if lower.endswith(".toml"):
        try:
            return tomllib.loads(raw_text), None
        except Exception as exc:
            return None, f"{rel}: invalid TOML ({exc})"
    if lower.endswith(".json"):
        try:
            return json.loads(raw_text), None
        except Exception as exc:
            return None, f"{rel}: invalid JSON ({exc})"
    if lower.endswith(".ini"):
        try:
            parser = configparser.ConfigParser()
            parser.optionxform = lambda optionstr: optionstr
            parser.read_string(raw_text)
            parsed_ini: dict[str, dict[str, str]] = {}
            if parser.defaults():
                parsed_ini["DEFAULT"] = dict(parser.defaults())
            for sec in parser.sections():
                parsed_ini[sec] = dict(parser.items(sec))
            return parsed_ini, None
        except Exception as exc:
            return None, f"{rel}: invalid INI ({exc})"
    return raw_text, None


def _check_file_inventory(
    expected_files: set[str], actual_files: set[str]
) -> list[str]:
    """Verify `configs/` contains exactly the expected static file paths."""
    errors: list[str] = []
    missing = sorted(expected_files - actual_files)
    unexpected = sorted(actual_files - expected_files)
    if missing:
        errors.append(
            f"Missing expected config files in configs/: {', '.join(missing)}"
        )
    if unexpected:
        errors.append(
            f"Unexpected files in configs/: {', '.join(unexpected)}"
        )
    return errors


def _validate_single_file(
    rel: str,
    raw_bytes: bytes,
    validator: Callable[[Any], list[str]] | None,
    extra_secret_keys: frozenset[str],
) -> list[str]:
    """Decode, secret-scan, parse, and run mod-specific validation for one file."""
    try:
        raw_text = raw_bytes.decode("utf-8")
    except UnicodeDecodeError as exc:
        return [f"{rel}: invalid UTF-8 ({exc})"]

    errors = scan_text_for_secrets(raw_text, rel)
    parsed, parse_error = _parse_static_config(rel, raw_text)
    if parse_error is not None:
        errors.append(parse_error)
        return errors

    if isinstance(parsed, (dict, list)):
        errors.extend(
            scan_mapping_for_secrets(
                parsed, rel, extra_key_names=extra_secret_keys
            )
        )

    if validator is not None:
        errors.extend(validator(parsed))

    return errors


def validate_static_configs(
    configs_dir: Path,
    static_files: Mapping[str, tuple[str, ...]],
    validators: Mapping[str, Callable[[Any], list[str]]] | None = None,
    *,
    forbidden_names: Iterable[str] = (),
    forbidden_suffixes: Iterable[str] = DEFAULT_FORBIDDEN_SUFFIXES,
    extra_secret_keys: frozenset[str] = frozenset(),
) -> dict[str, bytes]:
    """Run standard pre-flight checks on a static `configs/` directory and return file bytes."""
    if not configs_dir.is_dir():
        raise RuntimeError(f"Missing configs directory: {configs_dir}")

    errors = check_forbidden_entries(configs_dir, forbidden_names, forbidden_suffixes)
    config_files, collect_errors = collect_config_files(configs_dir)
    errors.extend(collect_errors)

    expected_files = set(static_files.keys())
    actual_files = set(config_files.keys())
    errors.extend(_check_file_inventory(expected_files, actual_files))

    loaded_bytes: dict[str, bytes] = {}
    for rel in sorted(actual_files & expected_files):
        raw_bytes = config_files[rel].read_bytes()
        loaded_bytes[rel] = raw_bytes
        validator = validators.get(rel) if validators else None
        errors.extend(
            _validate_single_file(rel, raw_bytes, validator, extra_secret_keys)
        )

    if errors:
        raise ValueError("Pre-flight validation failed:\n  - " + "\n  - ".join(errors))

    return loaded_bytes
