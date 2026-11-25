"""Minecraft client process detection."""

from __future__ import annotations

from typing import Any

import psutil

MC_CMDLINE_MARKERS = (
    "net.minecraft",
    "cpw.mods.bootstraplauncher",
    "net.minecraftforge",
    "modrinth",
    "prismlauncher",
)


def _is_java_minecraft_process(proc: psutil.Process) -> bool:
    info: dict[str, Any] = getattr(proc, "info", None) or proc.as_dict(attrs=["name", "cmdline"])
    name = (info.get("name") or "").lower()
    if "java" not in name:
        return False
    cmdline = " ".join(info.get("cmdline") or []).lower()
    return any(marker in cmdline for marker in MC_CMDLINE_MARKERS)


def default_is_minecraft_running() -> bool:
    """Return True if a Java Minecraft client process appears to be running."""
    for proc in psutil.process_iter(["name", "cmdline"]):
        try:
            if _is_java_minecraft_process(proc):
                return True
        except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
            continue
    return False
