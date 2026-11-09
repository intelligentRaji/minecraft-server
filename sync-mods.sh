#!/usr/bin/env bash
set -e
python3 "$(dirname "$0")/.agents/skills/minecraft-mod-manager/scripts/sync_mods.py" "$@"
