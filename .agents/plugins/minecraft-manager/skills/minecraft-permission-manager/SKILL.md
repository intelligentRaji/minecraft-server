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
Activate the **`minecraft-rcon`** skill to run the appropriate LuckPerms (`lp`) commands on `mc-forge-server`:

- **Grant a permission to a group or user:**
  - `lp group <group> permission set <node> true`
  - `lp user <uuid_or_name> permission set <node> true`
- **Deny or remove a permission:**
  - `lp group <group> permission set <node> false` *(explicit deny)*
  - `lp group <group> permission unset <node>` *(remove node)*
- **Audit current LuckPerms permissions:**
  1. Run `lp export <name>` via **`minecraft-rcon`**.
  2. Inspect `data/config/luckperms/<name>.json.gz` (using `zcat`), then remove the temporary export file.
