---
name: minecraft-mod-harness-manager
description: >-
  Configure onboarded mods under server/mods/<slug>/configs/ by loading per-mod
  AGENTS.md and <slug>-config/SKILL.md on demand, and create, maintain, audit,
  and remove per-mod slices under server/mods/<slug>/ — combining a non-AI Mod Bridge
  (configs/, sync.py, test_sync.py) with an AI Harness (server/mods/<slug>/AGENTS.md
  and server/mods/<slug>/.agents/skills/<slug>-config/SKILL.md).
---

# Minecraft Mod Bridge & AI Harness Lifecycle Runbook

Lifecycle runbook for configuring onboarded mods on demand and onboarding, maintaining, or removing per-mod slices under `server/mods/<slug>/`.

---

### Step 1: Configure an Onboarded Mod
Before reading, editing, or answering questions about an onboarded mod under `server/mods/<slug>/configs/`:

1. Read and follow the target mod's (avoiding unrelated mods' harnesses):
   - `server/mods/<slug>/AGENTS.md` *(rules, invariants, excluded files/keys)*
   - `server/mods/<slug>/.agents/skills/<slug>-config/SKILL.md` *(schemas, formatting, placeholders)*
2. Edit static configs in `server/mods/<slug>/configs/`. If the change alters an invariant or tracked file/key enforced by `server/mods/<slug>/sync.py`, also follow **Step 3**.
3. Run `python3 -m unittest server/mods/<slug>/test_sync.py -v` and `python3 server/mods/<slug>/sync.py --dry-run`, and tell the user if a `mc-forge-server` restart is required.

---

### Step 2: Onboard a Mod (Build Layer 1 Bridge + Layer 2 AI Harness)
1. Ensure the mod has booted at least once on `mc-forge-server` so its default configuration files exist in `server/data/config/` or `server/data/world/serverconfig/`.
2. Read the coordinator definition in [minecraft-mod-harness-manager/agent.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/agents/minecraft-mod-harness-manager/agent.md) (and specialist definitions in [mod-bridge-engineer/agent.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/agents/mod-bridge-engineer/agent.md), [mod-bridge-reviewer/agent.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/agents/mod-bridge-reviewer/agent.md), [mod-harness-architect/agent.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/agents/mod-harness-architect/agent.md), [mod-harness-reviewer/agent.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/agents/mod-harness-reviewer/agent.md) as needed).
3. Register `minecraft-mod-harness-manager` via `define_subagent` (`EnableSubagentTools: true`, `EnableWriteTools: false`) if not already registered, and invoke it via `invoke_subagent` for `<slug>`.

---

### Step 3: Maintain `sync.py` & `test_sync.py` When `configs/` Evolves
For long-term maintainability, every structural or rule-level change to `server/mods/<slug>/configs/` should be covered in `server/mods/<slug>/sync.py` and `server/mods/<slug>/test_sync.py`:
- **Config guardrail updates:** `server/mods/<slug>/sync.py` acts as a config guardrail—if fulfilling a user's configuration request legitimately requires changing a property or invariant enforced by `sync.py`, update `server/mods/<slug>/sync.py` and `server/mods/<slug>/test_sync.py` to match while preserving runtime-state isolation and secret guards.
- **New or removed config files** (e.g., after a mod update): Update `STATIC_FILES` / mixed-file mappings and `FORBIDDEN_NAMES` in `server/mods/<slug>/sync.py`.
- **New static vs. runtime-state keys:** Update key-level merge lists so live server state in `server/data/` continues to be preserved.
- **New invariants or schema expectations:** Add pre-flight validation checks in `server/mods/<slug>/sync.py` with self-explanatory error messages stating *why* the rule exists, and cover them with unit tests in `server/mods/<slug>/test_sync.py`.
- **Verify:** Run `python3 -m unittest server/mods/<slug>/test_sync.py -v` and `python3 server/mods/<slug>/sync.py --dry-run` after updating, and inform the user if a `mc-forge-server` restart is required for the updated config to take effect.

---

### Step 4: Remove a Mod Folder & AI Harness (On Mod Removal)
When a mod is uninstalled from `modpack/`, remove its `server/mods/<slug>/` directory:

```bash
# Preview removal:
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-harness-manager/scripts/remove_mod_harness.py <slug> --dry-run

# Remove mod slice:
python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-harness-manager/scripts/remove_mod_harness.py <slug>
```
