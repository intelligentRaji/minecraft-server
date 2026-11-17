# LuckPerms — Configuration Rules (`mods/luckperms/`)

## 1. Configuration Scope (`mods/luckperms/configs/`)
- Edit LuckPerms configuration files directly inside `mods/luckperms/configs/` (`luckperms.conf` and `contexts.json`).
- For section details, schema conventions, and invariants, activate the [`luckperms-config` skill](file:///home/wakaria/dev/minecraft-server/mods/luckperms/.agents/skills/luckperms-config/SKILL.md).

## 2. Server Invariants
1. **Local H2 Storage (`luckperms.conf`):**
   - `storage-method` **must** remain `"h2"`.
2. **Highest-Priority Prefix & Suffix Formatting (`luckperms.conf`):**
   - `meta-formatting.prefix.format` and `meta-formatting.suffix.format` **must** use `["highest"]`.
3. **Live LuckPerms Data Invariants:**
   - `group.default` **must** retain the 19 default Paradigm player permission nodes (`paradigm.msg`, `paradigm.reply`, `paradigm.mention.player`, `paradigm.spawn`, `paradigm.seen`, `paradigm.ignore`, `paradigm.home`, `paradigm.sethome`, `paradigm.delhome`, `paradigm.homes`, `paradigm.back`, `paradigm.tpa`, `paradigm.tpahere`, `paradigm.tpaccept`, `paradigm.tpdeny`, `paradigm.tpcancel`, `paradigm.warp`, `paradigm.warps`, and `paradigm.warp.info`).
   - Staff prefixes **must** end with an active trailing color code and no trailing `&r` (`&c&l[OWN] `, `&c[ADM] `, `&d[MOD] `) so Paradigm's `{prefix}{player_name}{suffix}` format colors prefix, nickname, and clan suffix uniformly.
   - FCM Clans manages user suffixes at priority `100` (`lp user <uuid> meta setsuffix 100 "<tag>"`). Never overwrite or clear user suffixes.

## 3. Sanitized & Excluded Files
- Never add `luckperms-h2-v2.mv.db` (or any `*.db`, `*.mv.db`, `*.jar`), `libs/`, `translations/`, `yaml-storage/`, `json-storage/`, `hocon-storage/`, `toml-storage/`, or `logs/` to `mods/luckperms/configs/`.
- Never commit non-empty database, Redis, or RabbitMQ credentials in `mods/luckperms/configs/luckperms.conf`.
