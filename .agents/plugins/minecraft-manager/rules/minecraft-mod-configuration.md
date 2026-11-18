---
trigger: always_on
description: Mandatory on-demand loading of per-mod AGENTS.md rules and <slug>-config skills when working with mod configurations
---

# Minecraft Mod Configuration

- **Load Per-Mod Harness On Demand:** Antigravity does **not** auto-discover `AGENTS.md` or `.agents/skills/` inside `server/mods/<slug>/` subfolders when running from the repository root. Before inspecting, editing, or answering questions about a mod's configuration under `server/mods/<slug>/configs/`, activate **`minecraft-mod-harness-manager`** and read/follow the target mod's `server/mods/<slug>/AGENTS.md` and `server/mods/<slug>/.agents/skills/<slug>-config/SKILL.md` (avoid loading unrelated mods' harnesses).
- **Source of Truth (`server/mods/<slug>/configs/`):** Edit static mod configs in `server/mods/<slug>/configs/` (synced to `server/data/` on `mc-forge-server` startup)—never edit static configs directly in `server/data/config/` or `server/data/world/serverconfig/`.
