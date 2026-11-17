---
name: create-config
description: Inspect and configure Create settings (worldgen, recipes, kinetics, stress values, contraptions, fluids, logistics, schematics, equipment, and trains) in mods/create/configs/.
---

# Create Configuration Guide (`create-config`)

Use this skill to inspect and modify **Create** (`modpack/server-client/create-1.20.1-6.0.8.jar`) configuration in `mods/create/configs/`.

> **Reload & Restart Behavior:** `config/create-common.toml` is a startup-only Forge common config (requires server restart). `world/serverconfig/create-server.toml` is a world serverconfig loaded on server/world start (or via `/create config` / Forge config reload where supported; restart the server to guarantee all changes apply cleanly).

---

## 1. Configuration Files Overview (`mods/create/configs/`)

| File | Scope & Purpose | Format |
| :--- | :--- | :--- |
| `config/create-common.toml` | Common Forge config controlling Create worldgen (`[worldgen]`). | TOML |
| `world/serverconfig/create-server.toml` | World server-side config for infrastructure, recipes, kinetics, stress values, contraptions, fluids, logistics, schematics, equipment, and trains. | TOML |

---

## 2. `config/create-common.toml` Reference

### `[worldgen]`
- `disableWorldGen` (boolean, default `false`): Prevents all worldgen added by Create (zinc ore, limestone, etc.) from taking effect.

---

## 3. `world/serverconfig/create-server.toml` Reference

### `[infrastructure]`
- `tickrateSyncTimer` (integer `> 5`, default `20`): Ticks the server waits before sending tickrate synchronization packets to keep client animations accurate below 20 TPS.

### `[recipes]`
- `bulkPressing` (boolean, default `false`): Allow Mechanical Press to process entire stacks at once.
- `bulkCutting` (boolean, default `false`): Allow Mechanical Saw to process entire stacks at once.
- `allowBrewingInMixer` (boolean, default `true`): Allow supported potions to be brewed by Mechanical Mixer + Basin.
- `allowShapelessInMixer` (boolean, default `true`): Allow shapeless crafting recipes in Mechanical Mixer + Basin.
- `allowShapedSquareInPress` (boolean, default `true`): Allow single-ingredient 2x2 or 3x3 crafting recipes in Mechanical Press + Basin.
- `allowRegularCraftingInCrafter` (boolean, default `true`): Allow standard crafting recipes in Mechanical Crafters.
- `maxFireworkIngredientsInCrafter` (integer `> 1`, default `9`): Maximum ingredients for crafting Firework Rockets in Mechanical Crafters.
- `allowStonecuttingOnSaw` (boolean, default `true`): Allow stonecutting recipes on Mechanical Saw.
- `allowCastingBySpout` (boolean, default `true`): Allow Spouts to interact with Tinkers' Construct Casting Tables and Basins.
- `displayLogStrippingRecipes` (boolean, default `true`): Display vanilla log-stripping interactions in JEI.
- `lightSourceCountForRefinedRadiance` (integer `> 1`, default `10`): Light sources destroyed before Chromatic Compound turns into Refined Radiance.
- `enableRefinedRadianceRecipe` (boolean, default `true`): Enable standard in-world Refined Radiance recipes.
- `enableShadowSteelRecipe` (boolean, default `true`): Enable standard in-world Shadow Steel recipe.

### `[kinetics]`
- `disableStress` (boolean, default `false`): Disable the Stress mechanic altogether.
- `maxBeltLength` (integer `> 5`, default `20`): Maximum length in blocks of mechanical belts.
- `maxChainConveyorLength` (integer `> 5`, default `32`): Maximum length in blocks of chain conveyor connections.
- `maxChainConveyorConnections` (integer `> 1`, default `4`): Maximum connections per chain conveyor.
- `crushingDamage` (integer `> 0`, default `4`): Damage dealt by active Crushing Wheels.
- `maxRotationSpeed` (integer `> 64`, default `256`): Maximum allowed rotation speed (RPM) for any Kinetic Block.
- `ignoreDeployerAttacks` (enum `"ALL"` | `"CREEPERS"` | `"NONE"`, default `"CREEPERS"`): Which mobs ignore Deployers when attacked by them.
- `kineticValidationFrequency` (integer `> 5`, default `60`): Game ticks between Kinetic Blocks checking whether their source is still valid.
- `crankHungerMultiplier` (float `0.0 ~ 1.0`, default `0.009999999776482582`): Exhaustion multiplier when turning a hand crank.
- `minimumWindmillSails` (integer `> 0`, default `8`): Sail-type blocks required for a windmill to assemble.
- `windmillSailsPerRPM` (integer `> 1`, default `8`): Sail-type blocks required to increase windmill speed by 1 RPM.
- `maxEjectorDistance` (integer `> 0`, default `32`): Max throw distance in blocks for a Weighted Ejector.
- `ejectorScanInterval` (integer `> 10`, default `120`): Ticks until the next item launched by an ejector scans blocks for collisions.

#### `[kinetics.encasedFan]`
- `fanPushDistance` (integer `> 5`, default `20`): Maximum push distance in blocks.
- `fanPullDistance` (integer `> 5`, default `20`): Maximum pull distance in blocks.
- `fanBlockCheckRate` (integer `> 10`, default `30`): Ticks between airflow obstruction checks.
- `fanRotationArgmax` (integer `> 64`, default `256`): RPM at which maximum fan stats are reached.
- `fanProcessingTime` (integer `> 0`, default `150`): Ticks required for a fan processing recipe.

#### `[kinetics.contraptions]`
- `maxBlocksMoved` (integer `> 1`, default `2048`): Maximum blocks movable by Pistons, Bearings, or other contraptions.
- `maxChassisRange` (integer `> 1`, default `16`): Maximum chassis attachment range.
- `maxPistonPoles` (integer `> 1`, default `64`): Maximum extension poles behind a Mechanical Piston.
- `maxRopeLength` (integer `> 1`, default `384`): Maximum rope length off a Rope Pulley.
- `maxCartCouplingLength` (integer `> 1`, default `32`): Maximum distance between two coupled minecarts.
- `rollerFillDepth` (integer `> 1`, default `12`): Maximum depth filled by a Mechanical Roller.
- `survivalContraptionPickup` (boolean, default `true`): Allow picking up minecart contraptions in survival mode.
- `movableSpawners` (enum `"MOVABLE"` | `"NO_PICKUP"` | `"UNMOVABLE"`, default `"NO_PICKUP"`): Contraption movement policy for Spawners.
- `amethystMovement` (enum `"MOVABLE"` | `"NO_PICKUP"` | `"UNMOVABLE"`, default `"NO_PICKUP"`): Contraption movement policy for Budding Amethyst.
- `movableObsidian` (enum `"MOVABLE"` | `"NO_PICKUP"` | `"UNMOVABLE"`, default `"UNMOVABLE"`): Contraption movement policy for Obsidian.
- `movableReinforcedDeepslate` (enum `"MOVABLE"` | `"NO_PICKUP"` | `"UNMOVABLE"`, default `"UNMOVABLE"`): Contraption movement policy for Reinforced Deepslate.
- `moveItemsToStorage` (boolean, default `true`): Place mined/harvested items into mounted contraption storage.
- `harvestPartiallyGrown` (boolean, default `false`): Allow harvesters to break crops that are not fully grown.
- `harvesterReplants` (boolean, default `true`): Replant crops after harvesting.
- `minecartContraptionInContainers` (boolean, default `false`): Allow placing minecart contraptions into container items.
- `stabiliseStableContraptions` (boolean, default `false`): Technical; create separated entity on non-rotating stabilised bearings.
- `syncPlayerPickupHitboxWithContraptionHitbox` (boolean, default `false`): Technical; expand player pickup hitbox to contraption hitbox.
- `noDropWhenContraptionReplaceBlocks` (boolean, default `false`): Prevent block drops when a contraption is placed inside in-world blocks.

#### `[kinetics.stats]`
- `mediumSpeed` (float `0.0 ~ 4096.0`, default `30.0`): Minimum RPM considered medium speed.
- `fastSpeed` (float `0.0 ~ 65535.0`, default `100.0`): Minimum RPM considered fast speed.
- `mediumStressImpact` (float `0.0 ~ 4096.0`, default `4.0`): Minimum SU impact considered medium.
- `highStressImpact` (float `0.0 ~ 65535.0`, default `8.0`): Minimum SU impact considered high.
- `mediumCapacity` (float `0.0 ~ 4096.0`, default `256.0`): Minimum SU capacity considered medium.
- `highCapacity` (float `0.0 ~ 65535.0`, default `1024.0`): Minimum SU capacity considered high.

#### `[kinetics.stressValues.v2.impact]`
Per-block stress impact in Stress Units (non-negative float `>= 0.0`; scaled by RPM):
- `0.0`: `brass_encased_shaft`, `clutch`, `gearbox`, `display_board`, `adjustable_chain_gearshift`, `rotation_speed_controller`, `stressometer`, `cogwheel`, `encased_chain_drive`, `belt`, `brass_encased_large_cogwheel`, `flywheel`, `speedometer`, `brass_encased_cogwheel`, `andesite_encased_shaft`, `sequenced_gearshift`, `andesite_encased_large_cogwheel`, `shaft`, `gearshift`, `andesite_encased_cogwheel`, `large_cogwheel`, `gantry_shaft`
- `1.0`: `chain_conveyor`, `cuckoo_clock`, `mysterious_cuckoo_clock`
- `2.0`: `mechanical_crafter`, `weighted_ejector`, `mechanical_arm`, `encased_fan`
- `4.0`: `turntable`, `mechanical_mixer`, `mechanical_bearing`, `copper_backtank`, `hose_pulley`, `millstone`, `sticky_mechanical_piston`, `deployer`, `elevator_pulley`, `mechanical_saw`, `mechanical_piston`, `clockwork_bearing`, `mechanical_drill`, `netherite_backtank`, `rope_pulley`, `mechanical_pump`
- `8.0`: `crushing_wheel`, `mechanical_press`

#### `[kinetics.stressValues.v2.capacity]`
Per-generator stress capacity in Stress Units (non-negative float `>= 0.0`):
- `steam_engine = 1024.0`, `water_wheel = 32.0`, `copper_valve_handle = 8.0`, `hand_crank = 8.0`, `creative_motor = 16384.0`, `large_water_wheel = 128.0`, `windmill_bearing = 512.0`

### `[fluids]`
- `fluidTankCapacity` (integer `> 1`, default `8`): Tank capacity in Buckets per block.
- `fluidTankMaxHeight` (integer `> 1`, default `32`): Maximum fluid tank height in blocks.
- `mechanicalPumpRange` (integer `> 1`, default `16`): Max push/pull distance in blocks on either side of a pump.
- `hosePulleyRange` (integer `> 1`, default `128`): Max distance a hose pulley can draw fluid blocks from.
- `hosePulleyBlockThreshold` (integer `> -1`, default `10000`): Minimum fluid blocks required to treat a body as an infinite source (`-1` disables).
- `fillInfinite` (boolean, default `false`): Allow hose pulleys to continue filling above-threshold sources.
- `bottomlessFluidMode` (enum `"ALLOW_ALL"` | `"DENY_ALL"` | `"ALLOW_BY_TAG"` | `"DENY_BY_TAG"`, default `"ALLOW_BY_TAG"`): Controls which fluids can be drained infinitely.
- `fluidFillPlaceFluidSourceBlocks` (boolean, default `true`): Allow hose pulleys to place fluid source blocks.
- `pipesPlaceFluidSourceBlocks` (boolean, default `true`): Allow open-ended pipes to place fluid source blocks.

### `[logistics]`
- `defaultExtractionTimer` (integer `> 1`, default `8`): Ticks a funnel waits between item transfers without redstone re-activation.
- `psiTimeout` (integer `> 1`, default `60`): Ticks a Portable Storage Interface waits for transfers before releasing contraptions.
- `mechanicalArmRange` (integer `> 1`, default `5`): Max reach in blocks of a Mechanical Arm.
- `packagePortRange` (integer `> 1`, default `5`): Max distance in blocks from a Package Port to its target.
- `linkRange` (integer `> 1`, default `256`): Max range in blocks of Redstone Link connections.
- `displayLinkRange` (integer `> 1`, default `64`): Max distance in blocks between Display Links and their target.
- `vaultCapacity` (integer `1 ~ 2048`, default `20`): Stacks an Item Vault holds per block in size.
- `chainConveyorCapacity` (integer `> 1`, default `20`): Packages a chain conveyor can carry at a time.
- `brassTunnelTimer` (integer `1 ~ 10`, default `10`): Ticks a Brass Tunnel waits between distributions.
- `factoryGaugeTimer` (integer `> 5`, default `100`): Ticks a Factory Gauge waits between requests.
- `seatHostileMobs` (boolean, default `true`): Whether hostile mobs walking near a seat start riding it.

### `[schematics]` & `[schematics.schematicannon]`
- `creativePrintIncludesAir` (boolean, default `false`): Whether placing a Schematic in Creative Mode replaces world blocks with Air.
- `maxSchematics` (integer `> 1`, default `10`): Uploaded schematics per player before older ones are overwritten.
- `maxTotalSchematicSize` (integer `> 16`, default `256`): Max uploaded schematic file size in KB.
- `maxSchematicPacketSize` (integer `256 ~ 32767`, default `1024`): Max packet size in Bytes for schematic uploads.
- `schematicIdleTimeout` (integer `> 100`, default `600`): Ticks without packets before an active schematic upload is discarded.
- `[schematics.schematicannon]`:
  - `schematicannonDelay` (integer `> 1`, default `10`): Ticks between Schematicannon shots (higher = slower).
  - `schematicannonShotsPerGunpowder` (integer `> 1`, default `400`): Blocks printed per Gunpowder item.

### `[equipment]`
- `maxSymmetryWandRange` (integer `> 10`, default `50`): Max distance to an active mirror for the Symmetry Wand.
- `placementAssistRange` (integer `> 3`, default `12`): Max distance for Create's placement assist.
- `toolboxRange` (integer `> 1`, default `10`): Max distance a Toolbox interacts with player inventories.
- `airInBacktank` (integer `> 1`, default `900`): Max air stored in a Backtank (seconds of underwater breathing).
- `enchantedBacktankCapacity` (integer `> 1`, default `300`): Air added per level of the Capacity enchantment.
- `maxExtendoGripActions` (integer `> 0`, default `1000`): Free Extendo Grip actions per filled Copper Backtank (`0` = unbreakable).
- `maxPotatoCannonShots` (integer `> 0`, default `200`): Free Potato Cannon shots per filled Copper Backtank (`0` = unbreakable).

### `[trains]`, `[trains.trainStats]`, `[trains.poweredTrainStats]`
- `trainsCauseDamage` (boolean, default `true`): Whether moving trains hurt colliding mobs and players.
- `maxTrackPlacementLength` (integer `16 ~ 128`, default `32`): Max track length placed in one batch or turn.
- `maxAssemblyLength` (integer `> 5`, default `128`): Max length of a Train Station's assembly track.
- `maxBogeyCount` (integer `> 1`, default `20`): Max bogeys assembled in a single train.
- `manualTrainSpeedModifier` (float `0.0 ~ 3.4028234663852886E38`, default `0.75`): Relative speed of manually controlled trains vs. scheduled trains.
- `[trains.trainStats]`: `trainTopSpeed` (`28.0`), `trainTurningTopSpeed` (`14.0`), `trainAcceleration` (`3.0`) (floats `>= 0.0`, blocks/s and blocks/s²).
- `[trains.poweredTrainStats]`: `poweredTrainTopSpeed` (`40.0`), `poweredTrainTurningTopSpeed` (`20.0`), `poweredTrainAcceleration` (`3.0`) (floats `>= 0.0`, blocks/s and blocks/s²).

---

## 4. Mandatory Invariants

1. **Valid TOML & Numeric Bounds:** Keep all keys/types valid TOML and within documented Forge ranges (e.g., `tickrateSyncTimer > 5`, `vaultCapacity` `1 ~ 2048`, `brassTunnelTimer` `1 ~ 10`, `maxSchematicPacketSize` `256 ~ 32767`, `maxTrackPlacementLength` `16 ~ 128`).
2. **Allowed Enum Values:** Only use documented enum strings for `ignoreDeployerAttacks`, contraption movement policies (`movableSpawners`, `amethystMovement`, `movableObsidian`, `movableReinforcedDeepslate`), and `bottomlessFluidMode`.
3. **Non-Negative Stress Values:** Every entry in `[kinetics.stressValues.v2.impact]` and `[kinetics.stressValues.v2.capacity]` must be `>= 0.0`.
4. **Excluded Runtime State:** Never place `data/world/schematics/`, `data/world/data/`, `data/world/playerdata/`, `data/logs/`, `data/mods/`, or binary/log artifacts (`*.db`, `*.jar`, `*.log`, `*.tmp`, `*.lock`, `*.nbt`) inside `mods/create/configs/`.
