---
name: luckperms-config
description: Inspect and configure LuckPerms settings (storage, meta-formatting, inheritance, contexts, and OP behavior) in mods/luckperms/configs/.
---

# LuckPerms Configuration Guide (`luckperms-config`)

Use this skill to inspect and modify **LuckPerms** configuration files in `mods/luckperms/configs/`.

---

## 1. Configuration Files Overview (`mods/luckperms/configs/`)

| File | Purpose & Key Settings | Format |
| :--- | :--- | :--- |
| `luckperms.conf` | Core LuckPerms configuration: server identity, storage backend, update propagation, meta formatting, inheritance/calculation, and OP integration. | HOCON |
| `contexts.json` | Static and default permission context key-value definitions applied to all players/checks. | JSON |

---

## 2. `luckperms.conf` Key Sections (HOCON)

### 2.1 Essential Settings
- `server` (default `"global"`): Server identifier used when evaluating `server=<name>` permission contexts.
- `use-server-uuid-cache` (default `false`): Whether LuckPerms uses the server's local UUID cache for username-to-UUID lookups.

### 2.2 Storage
- `storage-method` (must remain `"h2"`): Storage backend for permissions, groups, and user metadata.
- `data { ... }` / `messaging-service`: Connection blocks for remote databases, Redis, or RabbitMQ. Leave credentials empty/unused when running with `"h2"`.

### 2.3 Update Propagation
- `watch-files` (default `true`): Watches flat-file storage directories for external edits when using file-based storage.
- `auto-push-updates` (default `true`): Automatically pushes permission changes made via commands or API across linked servers when messaging is enabled.

### 2.4 Customization & Meta Formatting
- `temporary-add-behaviour` (default `"deny"`): Controls behavior when adding a temporary permission that already exists (`"deny"`, `"accumulate"`, or `"replace"`).
- `primary-group-calculation` (default `"parents-by-weight"`): Strategy for determining a user's primary group (`"stored"`, `"parents-by-weight"`, `"all-parents-by-weight"`).
- `auto-install-translations` (default `true`): Downloads/installs community translation bundles automatically.
- `meta-formatting`: Controls how prefixes and suffixes are stacked and formatted:
  - `meta-formatting.prefix.format` (must remain `["highest"]`)
  - `meta-formatting.suffix.format` (must remain `["highest"]`)
  - `duplicates` (`"first-only"`), `start-spacer` (`""`), `middle-spacer` (`" "`), `end-spacer` (`""`).

### 2.5 Inheritance & Calculation
- `inheritance-traversal-algorithm` (default `"depth-first-pre-order"`): Graph traversal order when resolving inherited group permissions.
- `context-satisfy-mode` (default `"at-least-one-value-per-key"`): How multi-valued contexts are matched during permission checks.
- `apply-wildcards` (default `true`): Enables `*` wildcard permission matching.
- `apply-regex` (default `true`): Enables `r=<pattern>` regular expression permission nodes.
- `apply-shorthand` (default `true`): Enables shorthand permission expansion (e.g., `some.perm.(a|b)`).

### 2.6 Fine Tuning
- `enable-ops` (default `true`): Allows Minecraft server operators (`ops.json`) to retain vanilla OP status alongside LuckPerms.
- `auto-op` (default `false`): Grants OP status automatically based on LuckPerms permissions (`luckperms.autoop`). Keep `false` to preserve explicit OP governance.
- `update-client-command-list` (default `true`): Sends updated Brigadier command trees to players when their permissions change.

---

## 3. `contexts.json` Schema (JSON)

`contexts.json` defines global context pairs as JSON objects:

```json
{
  "static-contexts": {},
  "default-contexts": {}
}
```

- `static-contexts`: Context key-value pairs always present for every permission check on this server.
- `default-contexts`: Fallback context key-value pairs applied when a query does not already specify that key.

---

## 4. Mandatory Server Invariants

1. **Storage Backend (`luckperms.conf`):**
   - `storage-method` **must** remain `"h2"`.
2. **Meta Formatting (`luckperms.conf`):**
   - `meta-formatting.prefix.format` and `meta-formatting.suffix.format` **must** remain `["highest"]`.
3. **Default Group Permissions (Live LuckPerms Data):**
   - `group.default` **must** retain the 19 default Paradigm player nodes: `paradigm.msg`, `paradigm.reply`, `paradigm.mention.player`, `paradigm.spawn`, `paradigm.seen`, `paradigm.ignore`, `paradigm.home`, `paradigm.sethome`, `paradigm.delhome`, `paradigm.homes`, `paradigm.back`, `paradigm.tpa`, `paradigm.tpahere`, `paradigm.tpaccept`, `paradigm.tpdeny`, `paradigm.tpcancel`, `paradigm.warp`, `paradigm.warps`, and `paradigm.warp.info`.
4. **Staff Prefix Formatting (Live LuckPerms Data):**
   - Staff prefixes **must** end with an active trailing color code and no trailing `&r` (`&c&l[OWN] `, `&c[ADM] `, `&d[MOD] `) so Paradigm's `{prefix}{player_name}{suffix}` format colors prefix, nickname, and clan suffix uniformly.
5. **FCM Clans Suffix Reservation (Live LuckPerms Data):**
   - FCM Clans manages user suffixes at priority `100` (`lp user <uuid> meta setsuffix 100 "<tag>"`). Never overwrite or clear user suffixes.
6. **Sanitized Configs Only:**
   - Never add `*.db`, `*.mv.db`, `*.jar`, `libs/`, `translations/`, `*-storage/`, or `logs/` to `mods/luckperms/configs/`, and never commit non-empty database, Redis, or RabbitMQ credentials.
