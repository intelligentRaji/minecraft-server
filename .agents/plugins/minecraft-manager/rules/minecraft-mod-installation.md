---
trigger: always_on
description: Declarative invariants and constraints for Minecraft mod management
---

# Minecraft Mod Governance & Invariants

### Platform Precedence & Fallback
- **Modrinth First:** Always query and install from Modrinth (API or catalog) for Minecraft 1.20.1 Forge by default.
- **Explicit Consent for Alternatives:** If a mod is absent from Modrinth, the agent must obtain user approval before downloading from alternative sources (e.g. CurseForge, GitHub). The request must provide: mod name, reason for absence, source URL, version, and mod loader.

### Mod Placement & Isolation
- **`server/modpack/server-client/`**: Content mods affecting world state, blocks, items, mobs, or dimensions. Required on both server and client.
- **`server/modpack/server-only/`**: Headless server utilities, pre-generation, performance, and backups. Excluded from client distribution.
- **`server/modpack/client-only/`**: Visual, rendering, audio, and HUD enhancements. Prohibited from server deployment to prevent headless crashes.

### State Consistency & Health Verification
- **Zero Drift Across All Targets:** The Docker server (`server/data/mods/`), the `modsync-api` manifest/distribution service, and the Google Drive backup (`minecraft-server/mods/`) must remain fully synchronized with their respective `server/modpack/` subfolders after any mod addition, upgrade, or removal. Any stale or removed mods must be pruned from Google Drive as well as local targets.
- **Boot Validation:** Any modification affecting server mods requires verifying container logs to confirm the server starts cleanly and reports ready state (`[DedicatedServer]: Done`) without dependency or runtime errors.
