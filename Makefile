.PHONY: help up up-proxy down restart logs modsync-logs status sync sync-dry backup lp-snapshot test client-build progress chunky-progress chunky-start chunky-pause chunky-continue chunky-cancel chunky-selection

COMPOSE := docker compose -f server/docker-compose.yml
SYNC_MODS := python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-manager/scripts/sync_mods.py
SYNC_DRIVE := python3 .agents/plugins/minecraft-manager/skills/minecraft-gdrive-sync/scripts/sync_mods_drive.py
LP_SNAPSHOT := python3 .agents/plugins/minecraft-manager/skills/minecraft-permission-manager/scripts/lp_snapshot.py
RCON_CLI := python3 .agents/plugins/minecraft-manager/skills/minecraft-rcon/scripts/rcon.py

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

up: ## Start Minecraft server + ModSync API (without public Caddy TLS proxy)
	$(COMPOSE) up -d --build

up-proxy: ## Start Minecraft server + ModSync API + Caddy HTTPS/WSS proxy (VPS)
	$(COMPOSE) --profile proxy up -d --build

down: ## Stop server stack
	$(COMPOSE) --profile proxy down

restart: ## Restart Minecraft server container
	$(COMPOSE) restart mc

logs: ## Follow Minecraft server logs in real-time
	$(COMPOSE) logs -f mc

modsync-logs: ## Follow ModSync API logs in real-time
	$(COMPOSE) logs -f modsync-api

status: ## Show container status
	$(COMPOSE) ps

sync: ## Synchronize server mods, restart mc if changed, and push WebSocket update
	$(SYNC_MODS) --restart

sync-dry: ## Preview server mod synchronization without modifying files
	$(SYNC_MODS) --dry-run

backup: ## Upload current modpack to Google Drive under minecraft-server/mods/
	$(SYNC_DRIVE)

lp-snapshot: ## Export LuckPerms snapshot via RCON to server/mods/luckperms/configs/
	$(LP_SNAPSHOT) --clean
	$(RCON_CLI) "lp export snapshot"
	$(LP_SNAPSHOT)

test: ## Run server, modsync-api, and client unit tests
	python3 -m unittest discover -s server -p "test_sync_mod_configurations.py"
	python3 -m unittest server/modsync_api/tests/test_manifest.py
	python3 -m unittest client/tests/test_syncer.py

client-build: ## Build standalone client binary via PyInstaller
	cd client && uv sync --group dev && uv run pyinstaller modsync.spec --clean --noconfirm

progress: chunky-progress ## Alias for chunky-progress

chunky-progress: ## Display Chunky pre-generation progress
	$(COMPOSE) exec mc rcon-cli chunky progress

chunky-start: ## Start Chunky chunk generation task
	$(COMPOSE) exec mc rcon-cli chunky start

chunky-pause: ## Pause Chunky generation task and save progress
	$(COMPOSE) exec mc rcon-cli chunky pause

chunky-continue: ## Continue paused Chunky generation task
	$(COMPOSE) exec mc rcon-cli chunky continue

chunky-cancel: ## Stop and delete current Chunky generation task
	$(COMPOSE) exec mc rcon-cli chunky cancel

chunky-selection: ## Display current Chunky shape and radius selection
	$(COMPOSE) exec mc rcon-cli chunky selection
