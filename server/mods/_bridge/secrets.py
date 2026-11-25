"""Secret-scanning guards for static mod configuration files."""

from __future__ import annotations

import re

SECRET_PATTERNS: tuple[tuple[str, re.Pattern[str]], ...] = (
    (
        "Discord Webhook URL",
        re.compile(
            r"https?://(?:ptb\.|canary\.)?discord(?:app)?\.com/api/webhooks/\d+/[\w-]+",
            re.IGNORECASE,
        ),
    ),
    (
        "Discord Bot Token",
        re.compile(r"[MN][A-Za-z\d]{23,}\.[\w-]{6}\.[\w-]{27,}"),
    ),
    (
        "Private Key",
        re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    ),
)

SECRET_KEY_NAMES: frozenset[str] = frozenset({
    "bottoken",
    "webhookurl",
    "password",
    "secret",
    "apikey",
    "accesstoken",
    "clientsecret",
})


def scan_mapping_for_secrets(
    obj: object,
    rel_path: str,
    key_path: str = "",
    *,
    extra_key_names: frozenset[str] = frozenset(),
) -> list[str]:
    """Recursively scan parsed JSON/TOML/YAML structures for secret keys or patterns."""
    errors: list[str] = []
    secret_keys = SECRET_KEY_NAMES | extra_key_names

    if isinstance(obj, dict):
        for k, v in obj.items():
            current_path = f"{key_path}.{k}" if key_path else str(k)
            if str(k).lower() in secret_keys and isinstance(v, str) and v.strip():
                errors.append(
                    f"{rel_path}: non-empty secret key '{current_path}' "
                    "(credentials and tokens must never be committed to static mod configs)"
                )
            errors.extend(
                scan_mapping_for_secrets(
                    v, rel_path, current_path, extra_key_names=extra_key_names
                )
            )
    elif isinstance(obj, list):
        for idx, item in enumerate(obj):
            errors.extend(
                scan_mapping_for_secrets(
                    item, rel_path, f"{key_path}[{idx}]", extra_key_names=extra_key_names
                )
            )
    elif isinstance(obj, str):
        for label, pattern in SECRET_PATTERNS:
            if pattern.search(obj):
                errors.append(
                    f"{rel_path}: detected {label} at '{key_path}' "
                    "(secrets must never be committed to static mod configs)"
                )
    return errors


def scan_text_for_secrets(text: str, rel_path: str) -> list[str]:
    """Scan raw text (e.g., HOCON or properties) for known secret patterns."""
    errors: list[str] = []
    for label, pattern in SECRET_PATTERNS:
        if pattern.search(text):
            errors.append(
                f"{rel_path}: detected {label} "
                "(secrets must never be committed to static mod configs)"
            )
    return errors
