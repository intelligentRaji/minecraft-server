# ExtraBotany — Configuration Rules (`server/mods/extrabotany/`)

## 1. Configuration Scope (`server/mods/extrabotany/configs/`)
- Edit ExtraBotany configuration directly inside `server/mods/extrabotany/configs/`:
  - `config/extrabotany-common.toml` — Forge common configuration covering telemetry settings, Gaia III boss disarm and spawn item/mod exemptions, the ExtraBotany fake player GameProfile identifier, and balance parameters for all 19 ExtraBotany functional and generating flowers.
- For full section/key schemas, default values, valid ranges, and operational notes, activate the [`extrabotany-config` skill](file:///home/wakaria/dev/minecraft-server/server/mods/extrabotany/.agents/skills/extrabotany-config/SKILL.md).

## 2. Server Invariants
1. **Exact Forge TOML Schema:**
   - `config/extrabotany-common.toml` must contain the exact table hierarchy `[server]`, `[server.telemetry]`, `[server.gaia]`, `[server.fakePlayer]`, and `[server.flower]` with all 19 flower subtables (`tradeOrchid`, `woodienia`, `reikarlily`, `bellflower`, `annoyingflower`, `stonesia`, `edelweiss`, `resoncund`, `sunshineLily`, `moonlightLily`, `twinstar`, `omniviolet`, `tinkle`, `bloodEnchantress`, `serenitian`, `mirrowtunia`, `necrofleur`, `manalink`, `enchanter`) and exact expected keys—no missing or extra keys anywhere.
2. **Telemetry, Gaia & Fake Player Bounds:**
   - `[server.telemetry].enableTelemetry` must be a strict boolean (`true` or `false`).
   - `[server.telemetry].telemetryUUID` must be a non-empty canonical 8-4-4-4-12 hexadecimal UUID string.
   - `[server.gaia].disableGaiaDisarm` must be a strict boolean (`true` or `false`).
   - `[server.gaia].gaiaSpawnUnCheckList` must be a list of non-empty strings formatted as mod IDs (e.g., `"minecraft"`) or `namespace:item` identifiers (e.g., `"sophisticatedbackpacks:backpack"`).
   - `[server.fakePlayer].fakePlayerId` must be a non-empty string (Forge GameProfile name used for permission and claim-protection integration).
3. **Flower Numeric & Cross-Field Bounds (`[server.flower.*]`):**
   - All mana, cost, cooldown, duration, transfer, transform, and temperature-max integer fields (`maxMana`, `manaCost`, `cooldown`, `workManaCost`, `produceCooldown`, `produceMana`, `passiveGenerateTime`, `passiveGenerateMana`, `spawnLightningCooldown`, `fishingCost`, `foodBoostMax`, `foodBoostPerEat`, `lossPerHeard`, `maxTemperatureCap`, `effectCost`, `transferSpeed`, `transformCost`, `consumeSpeed`) must be strict integers in `1..2147483647`.
   - `woodienia.range` must be a list of exactly 3 strict integers `[±X, +Y, ±Z]`, each in `0..2147483647`.
   - `serenitian.range` must be a strict integer in `1..16`.
   - `tradeOrchid.discountPercentage` and `annoyingflower.foodBoostCooldownMultiplier` must be finite numbers in `0.0..1.0`.
   - `bellflower.generateModify` must be a finite number in `0.0..2147483647.0`.
   - `twinstar.minTemperatureCap` must be a strict integer in `0..2147483647`, `twinstar.maxTemperatureCap` must be a strict integer in `1..2147483647`, and `minTemperatureCap <= maxTemperatureCap`.
4. **Startup / World-Load Restart Requirement:**
   - `config/extrabotany-common.toml` is a startup/world-load Forge TOML config (not live-reloadable via RCON); changes require a server restart to take effect.
   - Keep shared gameplay balance settings aligned with client distribution configs when applicable.

## 3. Security & Excluded Files
- **No Secrets or Credentials:** Never commit secrets, credentials, tokens, webhooks, or private keys—nor non-empty secret-bearing keys (`botToken`, `webhookUrl`, `password`, `secret`, `apiKey`, `accessToken`, `clientSecret`)—inside `server/mods/extrabotany/configs/`.
- **Excluded Config Scopes:** Do not place client-only (`extrabotany-client.toml`) or per-world server (`extrabotany-server.toml`) config files in `server/mods/extrabotany/configs/`.
- **Excluded Runtime & Binary Artifacts:** Never place symlinks, runtime/world directories (`world/`, `playerdata/`, `logs/`, `mods/`), or archive/binary/log files (`*.jar`, `*.db`, `*.sqlite`, `*.log`, `*.gz`, `*.zip`, `*.tar`, `*.tgz`, `*.bak`, `*.tmp`, `*.lock`) inside `server/mods/extrabotany/configs/`.
