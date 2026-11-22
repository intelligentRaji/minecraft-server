.PHONY: help up down restart reload logs modsync-logs status sync-dry lp-snapshot test client-build client-e2e invite-link chunky-progress chunky-start chunky-pause chunky-continue chunky-cancel chunky-selection

COMPOSE := docker compose
LP_SNAPSHOT := python3 .agents/plugins/minecraft-manager/skills/minecraft-permission-manager/scripts/lp_snapshot.py
RCON_CLI := python3 .agents/plugins/minecraft-manager/skills/minecraft-rcon/scripts/rcon.py

help: ## Show this help message
	@echo "Usage: make [target]"
	@echo ""
	@echo "Targets:"
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | awk 'BEGIN {FS = ":.*?## "}; {printf "  %-18s %s\n", $$1, $$2}'

up: ## Start Minecraft server + ModSync API + WireGuard
	$(COMPOSE) up -d --build

down: ## Stop server stack
	$(COMPOSE) down

restart: ## Ensure modsync-api is running and restart Minecraft server (syncs server mods & configs)
	$(COMPOSE) up -d --wait modsync-api
	$(COMPOSE) restart mc

reload: ## Refresh modsync-api manifest (pushes WS update only if server-client changed)
	@token="$${MODSYNC_ADMIN_TOKEN:-}"; \
	if [ -z "$$token" ] && [ -f .env ]; then token="$$(grep -E '^MODSYNC_ADMIN_TOKEN=' .env | head -n1 | cut -d= -f2-)"; fi; \
	curl -fsS -X POST -H "X-Admin-Token: $$token" http://127.0.0.1:8080/api/reload && echo ""

logs: ## Follow Minecraft server logs in real-time
	$(COMPOSE) logs -f mc

modsync-logs: ## Follow ModSync API logs in real-time
	$(COMPOSE) logs -f modsync-api

status: ## Show container status
	$(COMPOSE) ps

sync-dry: ## Preview server mod synchronization without modifying files
	python3 server/sync_mods.py --dry-run --skip-api

lp-snapshot: ## Export LuckPerms snapshot via RCON to server/mods/luckperms/configs/
	$(LP_SNAPSHOT) --clean
	$(RCON_CLI) "lp export snapshot"
	$(LP_SNAPSHOT)

test: ## Run server, CI, modsync-api, and client unit tests
	python3 -m unittest discover -s server -p "test_sync*.py"
	python3 -m unittest discover -s ci/tests -p "test_*.py" -v
	uv --directory modsync_api run pytest -v
	uv --directory client run pytest -v

client-build: ## Build standalone client binary via PyInstaller (host OS)
	cd client && uv sync --group dev && uv run pyinstaller modsync.spec --clean --noconfirm

client-e2e: ## Run cross-platform client E2E tests against built binary
	uv --directory client-e2e run pytest -v

invite-link: ## Print modsync:// invite link from .env (MODSYNC_SERVER_URL + MODSYNC_CLIENT_TOKEN)
	@url="$${MODSYNC_SERVER_URL:-}"; token="$${MODSYNC_CLIENT_TOKEN:-}"; \
	if [ -z "$$url" ] && [ -f .env ]; then url="$$(grep -E '^MODSYNC_SERVER_URL=' .env | head -n1 | cut -d= -f2-)"; fi; \
	if [ -z "$$token" ] && [ -f .env ]; then token="$$(grep -E '^MODSYNC_CLIENT_TOKEN=' .env | head -n1 | cut -d= -f2-)"; fi; \
	PYTHONPATH=client/src python3 -c "from modsync_client.config import build_invite_url; import sys; print(build_invite_url(sys.argv[1] or 'http://localhost:8080', sys.argv[2]))" "$$url" "$$token"

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
