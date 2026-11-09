.PHONY: help up down restart logs status sync sync-dry backup progress chunky-progress chunky-start chunky-pause chunky-continue chunky-cancel chunky-selection

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
