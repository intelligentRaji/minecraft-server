---
name: minecraft-permission-manager
description: >-
  Manage LuckPerms and Paradigm Essentials permission nodes for groups and players
  (grant, revoke, search, and audit permissions live without restarting the server).
---

# Minecraft Permission Management Runbook

Step-by-step procedure for inspecting, granting, and revoking LuckPerms permission nodes on the Docker Forge 1.20.1 server (`mc-forge-server`).

> **Note:** All permission changes apply **live with zero server restarts**.

---

### Step 1: Discover or Select Permission Nodes
- To look up available vanilla/modded command nodes without reading the full 300 KB JSON file, run `search_permissions.py`:
  ```bash
  python3 .agents/plugins/minecraft-manager/skills/minecraft-permission-manager/scripts/search_permissions.py <query>
  ```
- For a role-agnostic OP 3-equivalent command preset, see [op3-command-nodes.md](file:///home/wakaria/dev/minecraft-server/.agents/plugins/minecraft-manager/skills/minecraft-permission-manager/references/op3-command-nodes.md).
- For full-access groups (`owner`, `admin`), use the root wildcard `*` (`lp group <group> permission set * true`) to grant all Paradigm, vanilla, and modded permission nodes.

---

### Step 2: Apply or Audit Permissions via RCON
If targeting a specific player by nickname, resolve their offline UUID first using **`minecraft-role-manager`** (`resolve_player.py <nickname>`). Then activate **`minecraft-rcon`** to run LuckPerms (`lp`) commands on `mc-forge-server`:

- **Grant a permission to a group or user:**
  - `lp group <group> permission set <node> true`
  - `lp user <uuid_or_name> permission set <node> true`
- **Deny or remove a permission:**
  - `lp group <group> permission set <node> false` *(explicit deny)*
  - `lp group <group> permission unset <node>` *(remove node)*
- **Audit current LuckPerms permissions:** *(Note: `lp` commands run asynchronously and return empty stdout over `rcon-cli`.)*
  1. Run `lp export <name>` via **`minecraft-rcon`**.
  2. Inspect `server/data/config/luckperms/<name>.json.gz` (using `zcat`), then remove the temporary `.json.gz` export file when done (`lp export` will not overwrite an existing archive).

---

### Invariants & Guardrails
- **Base Player Permissions (`group.default`):** Keep the 19 default Paradigm player nodes on `group.default` (`paradigm.msg`, `paradigm.reply`, `paradigm.mention.player`, `paradigm.spawn`, `paradigm.seen`, `paradigm.ignore`, `paradigm.home`, `paradigm.sethome`, `paradigm.delhome`, `paradigm.homes`, `paradigm.back`, `paradigm.tpa`, `paradigm.tpahere`, `paradigm.tpaccept`, `paradigm.tpdeny`, `paradigm.tpcancel`, `paradigm.warp`, `paradigm.warps`, `paradigm.warp.info`).
- **Clan Suffix Reservation:** FCM Clans manages user suffixes at priority `100` (`lp user <uuid> meta setsuffix 100 "<tag>"`). Never overwrite or clear user suffixes when modifying permissions.
- **Static LuckPerms Configs:** Never store live databases or snapshot exports inside `server/mods/luckperms/configs/` (only `luckperms.conf` and `contexts.json` are tracked there).
