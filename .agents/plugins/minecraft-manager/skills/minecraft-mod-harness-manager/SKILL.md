---
name: minecraft-mod-harness-manager
description: >-
  Configure onboarded mods under mods/<slug>/configs/ by loading per-mod
  AGENTS.md and <slug>-config/SKILL.md on demand, and create, maintain, audit,
  and remove per-mod slices under mods/<slug>/ — combining a non-AI Mod Bridge
  (configs/, sync.py, test_sync.py) with an AI Harness (mods/<slug>/AGENTS.md
  and mods/<slug>/.agents/skills/<slug>-config/SKILL.md).
---

# Minecraft Mod Bridge & AI Harness Lifecycle Runbook

Procedure for configuring onboarded mods on demand and onboarding or removing a mod's vertical slice (`mods/<slug>/`) using the four-agent pipeline (`minecraft-mod-harness-manager` $\rightarrow$ `mod-bridge-engineer` $\rightarrow$ `mod-harness-architect` $\rightarrow$ `mod-harness-reviewer`).

---

### Step 1: Onboard a Mod (Build Layer 1 Bridge + Layer 2 AI Harness)
1. Ensure the mod has booted at least once on `mc-forge-server` so its default configuration files exist in `data/config/` or `data/world/serverconfig/`.
2. Read the subagent definitions in:
   - [minecraft-mod-harness-manager/agent.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/agents/minecraft-mod-harness-manager/agent.md) *(Coordinator)*
   - [mod-bridge-engineer/agent.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/agents/mod-bridge-engineer/agent.md) *(Stage 1: Non-AI Bridge — `configs/`, `sync.py`, `test_sync.py`)*
   - [mod-harness-architect/agent.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/agents/mod-harness-architect/agent.md) *(Stage 2: AI Harness — `mods/<slug>/AGENTS.md`, `mods/<slug>/.agents/skills/<slug>-config/SKILL.md`)*
   - [mod-harness-reviewer/agent.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/agents/mod-harness-reviewer/agent.md) *(Stage 3: End-to-End Auditor)*
3. Register `minecraft-mod-harness-manager` with `define_subagent` (`EnableSubagentTools: true`, `EnableWriteTools: false`) if not already registered in the session, and invoke it via `invoke_subagent` for `<slug>`:
   - **Stage 1 (`mod-bridge-engineer`):** Builds the non-AI Mod Bridge (`mods/<slug>/configs/`, `mods/<slug>/sync.py` executed by `mc-forge-server` on container start, and `mods/<slug>/test_sync.py`).
   - **Stage 2 (`mod-harness-architect`):** Designs `mods/<slug>/AGENTS.md` (at the mod root) and `mods/<slug>/.agents/skills/<slug>-config/SKILL.md` (focused strictly on how to work with the mod and its configurations, with zero mention of bridges, harnesses, or syncing).
   - **Stage 3 (`mod-harness-reviewer`):** Audits both Layer 1 and Layer 2.

---

### Step 2: Maintain `sync.py` & `test_sync.py` When `configs/` Evolves
For long-term maintainability, every structural or rule-level change to `mods/<slug>/configs/` should be covered in `mods/<slug>/sync.py` and `mods/<slug>/test_sync.py`:
- **Config guardrail updates:** `mods/<slug>/sync.py` acts as a config guardrail—if fulfilling a user's configuration request legitimately requires changing a property or invariant enforced by `sync.py`, update `mods/<slug>/sync.py` and `mods/<slug>/test_sync.py` to match while preserving runtime-state isolation and secret guards.
- **New or removed config files** (e.g., after a mod update): Update `STATIC_FILES` / mixed-file mappings and `FORBIDDEN_NAMES` in `mods/<slug>/sync.py`.
- **New static vs. runtime-state keys:** Update key-level merge lists so live server state in `data/` continues to be preserved.
- **New invariants or schema expectations:** Add pre-flight validation checks in `mods/<slug>/sync.py` with self-explanatory error messages stating *why* the rule exists, and cover them with unit tests in `mods/<slug>/test_sync.py`.
- **Verify:** Run `python3 -m unittest mods/<slug>/test_sync.py -v` and `python3 mods/<slug>/sync.py --dry-run` after updating, and inform the user if a `mc-forge-server` restart is required for the updated config to take effect.

---

### Step 3: Remove a Mod Folder & AI Harness (On Mod Removal)
When a mod is uninstalled from `modpack/`, remove its `mods/<slug>/` directory:

```bash
# Preview removal:
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-harness-manager/scripts/remove_mod_harness.py <slug> --dry-run

# Remove mod slice:
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-harness-manager/scripts/remove_mod_harness.py <slug>
```
