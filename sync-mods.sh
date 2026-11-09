#!/usr/bin/env bash
set -e
python3 "$(dirname "$0")/scripts/sync_mods.py" "$@"
