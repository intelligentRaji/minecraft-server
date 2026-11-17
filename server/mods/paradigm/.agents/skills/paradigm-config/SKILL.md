---
name: paradigm-config
description: Inspect and configure Paradigm Essentials settings (chat, tablist, MOTD, AFK, announcements, restarts, tickets, commands, cooldowns, holograms, emojis, and language strings) in mods/paradigm/configs/.
---

# Paradigm Essentials Configuration Guide (`paradigm-config`)

Use this skill to inspect and modify **Paradigm Essentials** configuration files in `mods/paradigm/configs/`.

---

## 1. Configuration Files Overview (`mods/paradigm/configs/`)

| File | Purpose & Key Settings | Schema Format |
| :--- | :--- | :--- |
| `main.json` | Master module switches (`announcementsEnable`, `motdEnable`, `restartEnable`, `mentionsEnable`, `discordIntegrationEnable`, `internalPermissionsEnable`), language (`language`), and teleportation/home defaults (`maxHomesDefault`, `rtpMaxDistance`, `rtpMinDistance`). | Wrapped `{"description", "value"}` |
| `chat.json` | Custom chat format (`enableCustomChatFormat`, `customChatFormat`, `playerNameHover`), private messages (`enablePrivateMessages`, `pmSenderFormat`, `pmReceiverFormat`), staff chat (`enableStaffChat`, `staffChatFormat`), and join/leave messages (`joinMessageFormat`, `leaveMessageFormat`). | Wrapped `{"description", "value"}` |
| `tablist.json` | Custom player list (`enabled`, `headerLines`, `footerLines`, `playerFormat`, `sortOrder`, `refreshInterval`) and `perWorldOverrides`. | Wrapped `{"description", "value"}` (except `perWorldOverrides`) |
| `motd.json` | In-game welcome MOTD (`motdLines`) and multiplayer server list ping (`serverlistMotdEnabled`, `serverlistLine1`, `serverlistLine2`, `serverlistPlayerHover`). | Wrapped `{"description", "value"}` (`motdLines` is raw list) |
| `afk.json` | AFK detection (`enabled`, `afkTimeoutSeconds`, `kickAfkPlayers`, `afkKickTimeoutSeconds`, `broadcastAfkStatus`, `afkPrefix`). | Wrapped `{"description", "value"}` |
| `announcements.json` | Scheduled chat broadcasts (`globalEnable`, `globalInterval`, `randomOrder`, `sound`, `messages`, `perWorldAnnouncements`). | Wrapped `{"description", "value"}` |
| `commands.json` | Per-command enable/disable map (`commands.<cmd>: true/false`) and `customAliases`. | Raw JSON |
| `commands/examples.json` | Custom command definition templates (`customCommands`). | Raw JSON |
| `cooldowns.json` | Per-command cooldown durations (`commandCooldownSeconds.<cmd>`) and warmup delays (`commandWarmupSeconds.<cmd>`) in seconds. | Raw JSON |
| `dashboard.json` | Web dashboard settings (`enabled`, `host`, `port`, `publicBaseUrl`, `requireLogin`, `sessionMinutes`). | Raw JSON |
| `emojis.json` | Chat emoji shortcodes (`emojis.<shortcode>` $\rightarrow$ symbol/color). | Raw JSON |
| `holograms.json` | Hologram subsystem settings (`enabled`, `defaultViewDistance`, `defaultRefreshIntervalSeconds`, `renderMode`). | Raw JSON |
| `lang/{cs,en,ru}.json` | Localized message templates for Czech, English, and Russian. | Raw JSON |
| `mentions.json` | Chat `@player` mentions (`MENTION_SYMBOL`, `MENTION_COLOR`, `SOUND_NAME`, `COOLDOWN_SECONDS`). | Wrapped `{"description", "value"}` |
| `moderation-settings.json` | Punishment broadcast toggles, appeal URLs, and ban/mute/kick screen templates. | Wrapped `{"description", "value"}` |
| `restarts.json` | Automated server restart scheduler (`restartType`, `realTimeInterval`, `fixedInterval`, warning broadcast intervals, `restartSound`). | Wrapped `{"description", "value"}` |
| `tickets.json` | Player support ticket settings (`enabled`, `maxOpenTicketsPerPlayer`, `createCooldownSeconds`) and `categories` list. | Wrapped `{"description", "value"}` (`categories` is raw list) |

---

## 2. Schema & Invariant Rules

1. **Wrapped vs. Raw Fields:**
   - In wrapped files (`main.json`, `chat.json`, `afk.json`, etc.), each setting is an object `{"description": "...", "value": <actual_value>}`. Always modify `.value` and keep `.description` intact.
   - In raw files (`commands.json`, `cooldowns.json`, `dashboard.json`, `emojis.json`, `holograms.json`, `lang/*.json`), edit the keys directly.
2. **Mandatory Server Invariants:**
   - `main.json`: `internalPermissionsEnable.value` **must** remain `false` (LuckPerms is the single source of truth for permissions and `{prefix}` / `{suffix}` metadata).
   - `chat.json`: `customChatFormat.value` **must** contain `{prefix}{player_name}{suffix}` without wrapping `{prefix}` or `{suffix}` in outer `<color:...>` tags.
   - `tablist.json`: `playerFormat.value` **must** contain `{prefix}{player_name}{suffix}`.
   - `cooldowns.json`: Contains **only** `commandCooldownSeconds` and `commandWarmupSeconds`.
   - `holograms.json`: Contains **only** `enabled`, `defaultViewDistance`, `defaultRefreshIntervalSeconds`, and `renderMode`.

---

## 3. Text Formatting (`<TAG>` & Legacy `&`) and Placeholders

### 3.1 Modern `<TAG>` Syntax
Used in `chat.json` (`customChatFormat`, `playerNameHover`), `tablist.json`, `motd.json`, `announcements.json`, `afk.json`, and `moderation-settings.json`:
- **Colors:** `<color:aqua>Text</color>`, `<color:#22D3EE>Text</color>`
- **Gradients & Rainbow:** `<gradient:#22D3EE:#A78BFA>Text</gradient>`, `<rainbow>Text</rainbow>`
- **Styles:** `<bold>`, `<italic>`, `<underline>`, `<strikethrough>`
- **Click & Hover Events:**
  - `<click:suggest_command:/msg {player_name} >...</click>`
  - `<click:run_command:/spawn>...</click>`
  - `<click:open_url:https://example.com>...</click>`
  - `<hover:'Tooltip text'>...</hover>`
- **Layout & Emojis:** `<center>Centered Line</center>`, `<emoji:star>`, `<emoji:heart>`

### 3.2 Legacy `&` Codes
Used in `chat.json` (`staffChatFormat`, `joinMessageFormat`, `leaveMessageFormat`), `restarts.json`, and `mentions.json`:
- Standard codes (`&0`–`&9`, `&a`–`&f`), hex (`&#RRGGBB`), styles (`&l` bold, `&o` italic, `&n` underline, `&m` strikethrough, `&r` reset).

### 3.3 Common Placeholders
- Player/Chat: `{prefix}`, `{player_name}`, `{display_name}`, `{suffix}`, `{message}`, `{world}`, `{ping}`
- Server/Tablist/MOTD: `{online}`, `{max_players}`, `{tps}`, `{mspt}`, `{uptime}`, `{memory_used}`, `{memory_max}`
