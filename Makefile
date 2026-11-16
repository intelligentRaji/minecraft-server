.PHONY: help up down restart logs status sync sync-dry backup config-pull config-pull-dry config-push config-push-dry config-diff config-unmapped lp-snapshot progress chunky-progress chunky-start chunky-pause chunky-continue chunky-cancel chunky-selection

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

up: config-push ## Sync all mod configs into data/ and start Minecraft server
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

LP_SNAPSHOT := python3 .agents/plugins/minecraft-manager/skills/minecraft-permission-manager/scripts/lp_snapshot.py
RCON_CLI := python3 .agents/plugins/minecraft-manager/skills/minecraft-rcon/scripts/rcon.py

config-pull: ## Pull runtime configs from data/ into each mods/<slug>/configs/
	@for script in mods/*/.agents/skills/*/scripts/sync_config.py; do \
		python3 "$$script" pull || exit 1; \
	done

config-pull-dry: ## Preview pulling runtime configs from data/ into mods/
	@for script in mods/*/.agents/skills/*/scripts/sync_config.py; do \
		python3 "$$script" pull --dry-run || exit 1; \
	done

config-push: ## Push all mods/*/configs/ into data/
	@for script in mods/*/.agents/skills/*/scripts/sync_config.py; do \
		python3 "$$script" push || exit 1; \
	done

config-push-dry: ## Preview pushing all mods/*/configs/ into data/
	@for script in mods/*/.agents/skills/*/scripts/sync_config.py; do \
		python3 "$$script" push --dry-run || exit 1; \
	done

config-diff: ## Show unified diff across all mods/*/configs/ vs data/
	@for script in mods/*/.agents/skills/*/scripts/sync_config.py; do \
		python3 "$$script" diff || exit 1; \
	done

config-unmapped: ## List config files in data/ not yet claimed by a mods/<slug>/ folder
	python3 .agents/plugins/minecraft-manager/skills/minecraft-mod-harness-manager/scripts/audit_unmapped.py

lp-snapshot: ## Export LuckPerms snapshot via RCON to mods/luckperms/configs/
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
