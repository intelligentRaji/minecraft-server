# Per-Mod Harness & Bridge Architecture (`mods/<slug>/`)

> **Companion To:**
> - [minecraft_mod_harness_config_tdd.md](./minecraft_mod_harness_config_tdd.md) *(Global Multi-Mod Architecture)*
>
> **Scope:** Standard anatomy, design rationale, and invariants for every per-mod vertical slice under `mods/<slug>/`.

---

## 1. Standard Per-Mod Layout (`mods/<slug>/`)

Every onboarded mod owns a self-contained directory at `mods/<slug>/` divided into two distinct layers:

```text
mods/<slug>/
│
├── ─── LAYER 1: NON-AI MOD BRIDGE (Systems, Placement & Tests) ─────────────
├── configs/                           # Sanitized static configurations (Git-tracked source of truth)
│   └── ...                            # (.json, .toml, .properties, .ini)
├── sync.py                            # Deterministic one-way placement & key-merge script -> /data/
├── test_sync.py                       # Automated unittest suite verifying sync.py without touching live data/
│
└── ─── LAYER 2: AI HARNESS (Pure Agent Rules & Domain Skill) ───────────────
    ├── AGENTS.md                      # Mod-root rules auto-loaded when touching mods/<slug>/
    └── .agents/
        └── skills/
            └── <slug>-config/
                └── SKILL.md           # Pure domain guide for configuring <slug> (zero Python scripts)
```

---

## 2. Why Each Component Exists & Lives Where It Does

### 2.1 Layer 1 — The Non-AI Mod Bridge (`configs/`, `sync.py`, `test_sync.py`)
The Mod Bridge is **100% independent of AI**. It works identically for human developers, `docker compose up`, and CI pipelines.

1. **`mods/<slug>/configs/` (Static Configuration Source of Truth):**
   - **Why:** Separates Git-tracked server configuration from the mutable runtime volume (`data/`).
   - **Why No `ctl.py` Wrapper:** Agents and humans already have `edit_file` / `read_file` to modify JSON/TOML files directly; `sync.py` handles all invariant and schema validation.
2. **`mods/<slug>/sync.py` (Startup-Only Placement & Merge):**
   - **Why at `mods/<slug>/sync.py`:** Sits at a fixed depth (`Path(__file__).resolve().parent`), eliminating directory walking (`find_repo_root()`) and working identically on the host and inside `mc-forge-server` (`/mods/<slug>/sync.py` $\rightarrow$ `/data`).
   - **Why Atomic Writes (`os.replace()`) + Mode/UID/GID Preservation:** Prevents half-written files and preserves existing permissions (`0600` / `0664`) and ownership (`1000:1000` via `os.chown` when container runs as `root`).
   - **Why Self-Explanatory Error Messages (No Redundant Invariant Comments):** Instead of burying rationale in comments above `if` checks, `sync.py` embeds the *why* directly into raised `ValueError` messages (e.g., why LuckPerms takes precedence over internal mod permissions, or why runtime keys are excluded). When a validation check fails on boot or in tests, the error immediately explains how to fix it and why the rule exists.
3. **`mods/<slug>/test_sync.py` (Isolated Verification):**
   - **Why:** Uses `tempfile.TemporaryDirectory` so every mod's placement logic, key-level merge behavior, permission preservation, `--dry-run`, idempotency, and invariant/secret guards are tested without mutating live `data/`.
   - **Maintainability Rule:** Whenever files, static/runtime keys, or invariants change in `mods/<slug>/configs/` (e.g., after a mod update), `mods/<slug>/sync.py` and `mods/<slug>/test_sync.py` are updated together.

### 2.2 Layer 2 — The AI Harness (`AGENTS.md`, `.agents/skills/<slug>-config/SKILL.md`)
The AI Harness wraps the mod's configuration files with progressive-disclosure instructions.

1. **`mods/<slug>/AGENTS.md` (At Mod Root, Not Inside `.agents/`):**
   - **Why at the mod root:** Antigravity's hierarchical rule discovery walks up from any edited file in `mods/<slug>/configs/` to load `mods/<slug>/AGENTS.md` automatically.
   - **Content:** Concise non-negotiable guardrails—configuration scope, required server invariants, and forbidden runtime/secret files or keys.
2. **`mods/<slug>/.agents/skills/<slug>-config/SKILL.md` (Pure Mod-Domain Skill):**
   - **Why zero Python scripts inside `.agents/`:** Keeps `.agents/` strictly to AI instructions; all executable code lives in Layer 1.
   - **Why zero meta-architecture or sync instructions:** `SKILL.md` teaches the agent **only** how to work with that specific mod and its config files (file layout, schema conventions, formatting syntax, placeholders, invariants). Synchronization happens automatically on `mc-forge-server` container startup—skills never instruct agents to sync `data/` with the repo.

---

## 3. Three-Tier File Classification Model

Before creating `mods/<slug>/configs/` and `mods/<slug>/sync.py`, every file belonging to `<slug>` in `data/config/` and `data/world/serverconfig/` is classified into one of three tiers:

| Tier | Description | Tracked in `mods/<slug>/configs/`? | `mods/<slug>/sync.py` Placement Behavior |
| :--- | :--- | :--- | :--- |
| **1. Pure Static Configuration** | Settings modified only by administrators in the repo (e.g., gameplay `.toml` files, chat/MOTD templates, language files). | **Yes** (full file) | Atomic whole-file replacement (`os.replace()`) when SHA-256 differs. |
| **2. Mixed Static Config + Runtime State** | Files that mix static admin settings with live server-mutated state (e.g., per-player UUID maps, active timers, in-game placed objects). | **Yes (Sanitized):** Only static keys are stored; runtime keys are stripped. | **Atomic key-level merge:** Reads existing file in `data/`, preserves live runtime keys, updates only static keys, and writes via `os.replace()` if changed. |
| **3. Excluded Runtime State & Secrets** | Files mutated dynamically in-game (player locations/inventories, world coordinates, databases, caches, downloaded libraries) or containing secrets (tokens, passwords, webhooks, connection URIs). | **No (Forbidden)** | Never copied to `mods/<slug>/configs/` and never touched by `sync.py`. |

---

## 4. Reference Implementation: `mods/paradigm/`

[mods/paradigm/](file:///home/wakaria/dev/minecraft-server/mods/paradigm) serves as the reference implementation of this specification:
- **Layer 1:** `configs/` (17 pure static JSONs + sanitized `cooldowns.json` and `holograms.json`), [sync.py](file:///home/wakaria/dev/minecraft-server/mods/paradigm/sync.py) (atomic copies + key-level merges + LuckPerms/formatting invariants + secret scan), and [test_sync.py](file:///home/wakaria/dev/minecraft-server/mods/paradigm/test_sync.py) (8 passing tests).
- **Layer 2:** [AGENTS.md](file:///home/wakaria/dev/minecraft-server/mods/paradigm/AGENTS.md) at mod root and [SKILL.md](file:///home/wakaria/dev/minecraft-server/mods/paradigm/.agents/skills/paradigm-config/SKILL.md) registered in [.agents/skills.json](file:///home/wakaria/dev/minecraft-server/.agents/skills.json).
