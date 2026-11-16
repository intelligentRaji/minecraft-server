.PHONY: help up down restart logs status sync sync-dry backup config-pull config-pull-dry config-push config-push-dry config-diff lp-snapshot progress chunky-progress chunky-start chunky-pause chunky-continue chunky-cancel chunky-selection

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

up: ## Start Minecraft server in background
	docker compose up -d

down: ## Stop Minecraft server
	docker compose down

restart: ## Restart Minecraft server container
	docker compose restart mc

logs: ## Follow server logs in real-time
	docker compose logs -f mc

status: ## Show container status
	docker compose ps

sync: ## Synchronize mods and restart server if server mods changed
	python3 .agents/skills/minecraft-mod-manager/scripts/sync_mods.py --restart

sync-dry: ## Preview modpack synchronization without modifying files
	python3 .agents/skills/minecraft-mod-manager/scripts/sync_mods.py --dry-run

backup: ## Upload mods to Google Drive under minecraft-server/mods/
	python3 .agents/skills/minecraft-mod-manager/scripts/upload_to_gdrive.py

CONFIG_SYNC_DIR := .agents/plugins/minecraft-manager/skills/minecraft-config-sync/scripts
LP_SNAPSHOT := python3 .agents/plugins/minecraft-manager/skills/minecraft-permission-manager/scripts/lp_snapshot.py
RCON_CLI := python3 .agents/plugins/minecraft-manager/skills/minecraft-rcon/scripts/rcon.py

config-pull: ## Pull allowlisted server configs from data/ into server-config/
	python3 $(CONFIG_SYNC_DIR)/pull_configs.py

config-pull-dry: ## Preview config pull without modifying files
	python3 $(CONFIG_SYNC_DIR)/pull_configs.py --dry-run

config-push: ## Apply versioned configs from server-config/ into data/
	python3 $(CONFIG_SYNC_DIR)/push_configs.py

config-push-dry: ## Preview config push without modifying files
	python3 $(CONFIG_SYNC_DIR)/push_configs.py --dry-run

config-diff: ## Show unified diff between server-config/ and data/
	python3 $(CONFIG_SYNC_DIR)/diff_configs.py

lp-snapshot: ## Export LuckPerms snapshot via RCON to server-config/
	$(LP_SNAPSHOT) --clean
	$(RCON_CLI) "lp export snapshot"
	$(LP_SNAPSHOT)

progress: chunky-progress ## Alias for chunky-progress

chunky-progress: ## Display Chunky pre-generation progress
	docker compose exec mc rcon-cli chunky progress

chunky-start: ## Start Chunky chunk generation task
	docker compose exec mc rcon-cli chunky start

chunky-pause: ## Pause Chunky generation task and save progress
	docker compose exec mc rcon-cli chunky pause

chunky-continue: ## Continue paused Chunky generation task
	docker compose exec mc rcon-cli chunky continue

chunky-cancel: ## Stop and delete current Chunky generation task
	docker compose exec mc rcon-cli chunky cancel

chunky-selection: ## Display current Chunky shape and radius selection
	docker compose exec mc rcon-cli chunky selection
