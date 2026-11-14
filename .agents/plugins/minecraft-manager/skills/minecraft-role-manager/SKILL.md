---
name: minecraft-role-manager
description: >-
  Assign, update, or remove Minecraft server roles (owner, admin, moderator, player)
  by player nickname, synchronizing visual team prefixes/colors, LuckPerms groups, and OP status.
---

# Minecraft Role Management Runbook

Step-by-step procedure for assigning or revoking player roles by nickname on the Docker Forge 1.20.1 server (`mc-forge-server`).

---

## Role Definitions

| Role | Team / LP Group | Prefix | Color | LP Weight | OP Level | Rights Summary |
| :--- | :--- | :--- | :--- | :--- | :--- | :--- |
| **Owner** | `owner` | `[OWN] ` *(bold red)* | `red` | `100` | `4` | Full server control (`/stop`, `/save-all`, `/op`, all Paradigm/mod commands) via OP 4 + LuckPerms `*` wildcard |
| **Admin** | `admin` | `[ADM] ` *(red)* | `red` | `80` | `4` | Full OP 4 control (live via `op <name>`, no restart) + LuckPerms `*` wildcard (all Paradigm/mod commands) |
| **Moderator** | `moderator` | `[MOD] ` *(purple)* | `light_purple` | `60` | `0` | OP 3-equivalent moderation & gameplay commands via LuckPerms + Paradigm (live, no restart) |
| **Player** | `default` *(no team)* | *(no prefix)* | Default | `10` | `0` | Normal survival gameplay + `CoreCommands` player commands |

> **Note:** All role assignments apply **live with zero server restarts**.

---

### Step 1: Resolve Player Identity
Run `resolve_player.py` to get the player's exact `name` and offline `uuid` from `data/usercache.json`:

```bash
python3 .agents/plugins/minecraft-manager/skills/minecraft-role-manager/scripts/resolve_player.py <nickname>
```

---

### Step 2: Apply Role via RCON
Activate the **`minecraft-rcon`** skill to execute the appropriate commands on `mc-forge-server` using the resolved `name` and `uuid` (falling back to `name` if `uuid` is `null`):

- **Assign `owner`, `admin`, or `moderator`:**
  1. `team join <role> <name>`
  2. `lp user <uuid_or_name> parent set <role>`
  3. `op <name>` *(for `owner` / `admin`)* **or** `deop <name>` *(for `moderator`)*
  4. `team list <role>` *(verification)*

- **Assign `player` (revoke elevated role):**
  1. `team leave <name>`
  2. `lp user <uuid_or_name> parent set default`
  3. `deop <name>`

- **One-time group/team setup** *(only needed if teams or LuckPerms groups do not exist yet)*:
  - Teams: `team add <role>`, `team modify <role> color <color>`, `team modify <role> prefix <json>`
  - LuckPerms: `lp creategroup <role>`, `lp group <role> setweight <weight>`, `lp group <role> meta setprefix <weight> "<prefix>"`
