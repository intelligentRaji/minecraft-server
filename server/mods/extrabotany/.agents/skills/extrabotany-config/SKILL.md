---
name: extrabotany-config
description: Inspect and configure ExtraBotany common settings (telemetry, Gaia III disarm and spawn exemptions, fake player ID, and all 19 flower mana/cooldown/range settings) in server/mods/extrabotany/configs/.
---

# ExtraBotany Configuration Guide (`extrabotany-config`)

Use this skill to inspect and modify **ExtraBotany** (`modpack/server-client/extrabotany-forge-1.20.1-1.9.2.jar`) configuration in `server/mods/extrabotany/configs/`.

> **Dependency & Reload Notes:**
> - `extrabotany-forge-1.20.1-1.9.2.jar` depends on `eventwrapper-forge-1.20.1-1.1.4.jar`, which ships no configuration files of its own.
> - `config/extrabotany-common.toml` is a startup/world-load Forge TOML configuration and is **not live-reloadable via RCON**; restart the server after changes for them to take effect.

---

## 1. Configuration File Overview (`server/mods/extrabotany/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/extrabotany-common.toml` | Forge common settings: telemetry opt-in/UUID, Gaia III disarm toggle and spawn item/mod exemption list, fake player GameProfile ID, and mana/cooldown/range/multiplier parameters for all 19 ExtraBotany flowers. | TOML |

---

## 2. `config/extrabotany-common.toml` Reference

All settings reside under the `[server]` table and its nested subtables. Every expected section and key must remain present with no extra or omitted keys.

### `[server.telemetry]`
- `enableTelemetry` (boolean, default `true`): Enables anonymous gameplay telemetry collection (e.g., Gaia III completion rate). Set to `false` to opt out.
- `telemetryUUID` (string, default `"4ddf92ed-0894-46bf-85f3-acfa0d9e0fe1"`): Canonical `8-4-4-4-12` hexadecimal UUID identifying this server instance for telemetry.

### `[server.gaia]`
- `disableGaiaDisarm` (boolean, default `false`): Set to `true` to disable the Gaia Guardian's disarming ability.
- `gaiaSpawnUnCheckList` (array of non-empty strings, default `["minecraft", "botania", "extrabotany"]`): Mod IDs or `namespace:item` item identifiers exempt from Gaia III spawn equipment/inventory checks (e.g., `"minecraft"`, `"sophisticatedbackpacks:backpack"`).

### `[server.fakePlayer]`
- `fakePlayerId` (non-empty string, default `"[Extrabotany]"`): Forge `GameProfile` name used by ExtraBotany's fake player for permission and land-claim protection checks.

---

### `[server.flower]` — All 19 Flower Subtables

Unless otherwise noted, all integer fields use strict 32-bit integer bounds `1..2147483647`.

#### `[server.flower.tradeOrchid]` (Trade Orchid)
- `maxMana` (integer `1..2147483647`, default `10000`): Maximum mana buffer.
- `manaCost` (integer `1..2147483647`, default `1000`): Mana consumed per villager trade discount operation.
- `cooldown` (integer `1..2147483647`, default `40`): Cooldown interval in ticks.
- `discountPercentage` (finite number `0.0..1.0`, default `0.5`): Price multiplier/discount fraction (supports up to `0.01` precision; e.g., `0.85` = 15% off).

#### `[server.flower.woodienia]` (Woodienia)
- `maxMana` (integer `1..2147483647`, default `10000`): Maximum mana buffer.
- `workManaCost` (integer `1..2147483647`, default `200`): Mana consumed when breaking a log block.
- `range` (array of 3 integers, each `0..2147483647`, default `[8, 16, 8]`): Working search volume centered on the flower as `[±X, +Y, ±Z]`.
- `cooldown` (integer `1..2147483647`, default `10`): Work interval in ticks.

#### `[server.flower.reikarlily]` (Reikarlily)
- `maxMana` (integer `1..2147483647`, default `12000`): Maximum mana buffer.
- `produceCooldown` (integer `1..2147483647`, default `3600`): Cooldown in ticks before mana can be regenerated again after a lightning strike.
- `produceMana` (integer `1..2147483647`, default `12000`): Instant mana burst generated per lightning strike.
- `passiveGenerateTime` (integer `1..2147483647`, default `1500`): Duration in ticks of passive mana generation following a lightning strike.
- `passiveGenerateMana` (integer `1..2147483647`, default `45`): Mana generated per tick during the post-strike passive phase.
- `spawnLightningCooldown` (integer `1..2147483647`, default `3600`): Cooldown in ticks for summoning lightning during rain.

#### `[server.flower.bellflower]` (Bellflower)
- `maxMana` (integer `1..2147483647`, default `300`): Maximum mana buffer.
- `generateModify` (finite number `0.0..2147483647.0`, default `1.0`): Multiplier applied to wind-based mana generation.

#### `[server.flower.annoyingflower]` (Annoying Flower)
- `maxMana` (integer `1..2147483647`, default `1000`): Maximum mana buffer.
- `fishingCost` (integer `1..2147483647`, default `300`): Mana consumed per fishing cycle.
- `cooldown` (integer `1..2147483647`, default `900`): Base working cooldown in ticks.
- `foodBoostMax` (integer `1..2147483647`, default `12`): Maximum accumulated food-boost charges.
- `foodBoostPerEat` (integer `1..2147483647`, default `3`): Boost charges gained per food item consumed.
- `foodBoostCooldownMultiplier` (finite number `0.0..1.0`, default `0.4`): Cooldown multiplier applied while food-boosted.

#### `[server.flower.stonesia]` (Stonesia)
- `maxMana` (integer `1..2147483647`, default `3200`): Maximum mana buffer.
- `cooldown` (integer `1..2147483647`, default `40`): Work cooldown in ticks.

#### `[server.flower.edelweiss]` (Edelweiss)
- `maxMana` (integer `1..2147483647`, default `12800`): Maximum mana buffer.
- `cooldown` (integer `1..2147483647`, default `40`): Work cooldown in ticks.

#### `[server.flower.resoncund]` (Resoncund)
- `maxMana` (integer `1..2147483647`, default `1200`): Maximum mana buffer.
- `lossPerHeard` (integer `1..2147483647`, default `50`): Mana generation penalty applied each time the same sound is repeatedly heard.

#### `[server.flower.sunshineLily]` (Sunshine Lily)
- `maxMana` (integer `1..2147483647`, default `200`): Maximum mana buffer.
- `produceMana` (integer `1..2147483647`, default `2`): Mana generated per production step.

#### `[server.flower.moonlightLily]` (Moonlight Lily)
- `maxMana` (integer `1..2147483647`, default `200`): Maximum mana buffer.
- `produceMana` (integer `1..2147483647`, default `1`): Mana generated per production step.

#### `[server.flower.twinstar]` (Twinstar)
- `maxMana` (integer `1..2147483647`, default `1000`): Maximum mana buffer.
- `maxTemperatureCap` (integer `1..2147483647`, default `2147483647`): Maximum accepted fluid temperature.
- `minTemperatureCap` (integer `0..2147483647`, default `0`): Minimum accepted fluid temperature. Must satisfy `minTemperatureCap <= maxTemperatureCap`.

#### `[server.flower.omniviolet]` (Omniviolet)
- `maxMana` (integer `1..2147483647`, default `1500`): Maximum mana buffer.

#### `[server.flower.tinkle]` (Tinkle)
- `maxMana` (integer `1..2147483647`, default `1000`): Maximum mana buffer.
- `produceMana` (integer `1..2147483647`, default `100`): Mana generated per production step.

#### `[server.flower.bloodEnchantress]` (Blood Enchantress)
- `maxMana` (integer `1..2147483647`, default `800`): Maximum mana buffer.
- `produceMana` (integer `1..2147483647`, default `22`): Mana generated per production step.

#### `[server.flower.serenitian]` (Serenitian)
- `range` (integer `1..16`, default `3`): Working radius in blocks.

#### `[server.flower.mirrowtunia]` (Mirrowtunia)
- `maxMana` (integer `1..2147483647`, default `2000`): Maximum mana buffer.
- `effectCost` (integer `1..2147483647`, default `100`): Mana consumed per potion effect applied.

#### `[server.flower.necrofleur]` (Necrofleur)
- `maxMana` (integer `1..2147483647`, default `200`): Maximum mana buffer.

#### `[server.flower.manalink]` (Manalink)
- `transferSpeed` (integer `1..2147483647`, default `400`): Mana transfer rate per cycle.

#### `[server.flower.enchanter]` (Enchanter)
- `transformCost` (integer `1..2147483647`, default `250000`): Total mana required to transform grass into Enchanted Soil.
- `consumeSpeed` (integer `1..2147483647`, default `400`): Mana consumption rate per cycle.

---

## 3. Mandatory Invariants & Excluded Files

1. **Exact Schema & Key Parity:**
   - Keep `[server]`, `[server.telemetry]`, `[server.gaia]`, `[server.fakePlayer]`, `[server.flower]`, and all 19 `[server.flower.*]` tables intact with no missing or extra keys.
2. **Types, Formats & Numeric Bounds:**
   - Keep `enableTelemetry` and `disableGaiaDisarm` as strict booleans.
   - Keep `telemetryUUID` as a non-empty canonical `8-4-4-4-12` hex UUID string.
   - Keep `fakePlayerId` as a non-empty string and `gaiaSpawnUnCheckList` as a list of non-empty mod ID or `namespace:item` strings.
   - Respect every numeric bound above: standard flower integers in `1..2147483647`, `woodienia.range` as 3 integers in `0..2147483647`, `serenitian.range` in `1..16`, `tradeOrchid.discountPercentage` and `annoyingflower.foodBoostCooldownMultiplier` as finite numbers in `0.0..1.0`, `bellflower.generateModify` in `0.0..2147483647.0`, `twinstar.minTemperatureCap` in `0..2147483647`, `twinstar.maxTemperatureCap` in `1..2147483647`, and `minTemperatureCap <= maxTemperatureCap`.
3. **Restart Discipline:**
   - `config/extrabotany-common.toml` is not live-reloadable via RCON; restart the server after editing.
4. **Security & Excluded Files:**
   - Never commit secrets, credentials, tokens, webhooks, or private keys (nor non-empty secret keys such as `botToken`, `webhookUrl`, `password`, `secret`, `apiKey`, `accessToken`, `clientSecret`).
   - Do not include client-only (`extrabotany-client.toml`) or per-world server (`extrabotany-server.toml`) config files in `server/mods/extrabotany/configs/`.
   - Never place symlinks, runtime/world directories (`world/`, `playerdata/`, `logs/`, `mods/`), or archive/binary/log files (`*.jar`, `*.db`, `*.sqlite`, `*.log`, `*.gz`, `*.zip`, `*.tar`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`) inside `server/mods/extrabotany/configs/`.
