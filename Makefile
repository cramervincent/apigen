# ====================================================================================
# Makefile for Managing the Docker Compose Application
# Contains safe workflows for both Development and Production.
# ====================================================================================

# --- Variables ---
PULL_BRANCH := main
APP_SERVICE_NAME := apigen
# NIEUW: Expliciet pad naar de Alembic configuratie binnen de container
ALEMBIC_CONFIG_PATH := /app/alembic.ini

.DEFAULT_GOAL := help

# ====================================================================================
# DOCUMENTATION
# ====================================================================================

help:
	@echo "Usage: make <target>"
	@echo ""
	@echo "------------------ Development Environment ------------------"
	@echo "  up                   Builds and starts all services in the background."
	@echo "  down                 Stops and removes the containers and network."
	@echo "  logs                 Shows and follows the logs from all services."
	@echo "  reset                (DESTRUCTIVE) Stops, removes containers AND data, and restarts."
	@echo "  shell                Opens a bash shell inside the running application container."
	@echo ""
	@echo "------------------ Database Migrations (for Development) ------------------"
	@echo "  db-makemigration m=\"...\" Creates a new database migration file inside the container."
	@echo "  db-upgrade           Manually applies all pending migrations to the database."
	@echo ""
	@echo "------------------ Production Environment -------------------"
	@echo "  production-update    Pulls the latest code and safely restarts the application."
	@echo ""


# ====================================================================================
# DEVELOPMENT ENVIRONMENT COMMANDS
# ====================================================================================

up:
	docker compose up -d --build

down:
	docker compose down

logs:
	docker compose logs -f

reset:
	@echo "WARNING: This will delete all containers and data volumes."
	docker compose down -v
	make up

shell:
	docker compose exec $(APP_SERVICE_NAME) bash


# ====================================================================================
# DATABASE MIGRATIONS (for Development use)
# ====================================================================================

# AANGEPAST: -c vlag toegevoegd om expliciet het pad naar alembic.ini te specificeren.
db-makemigration:
ifndef m
	$(error Usage: make db-makemigration m="<your_message>")
endif
	@echo "Creating new migration with message: $(m)"
	docker compose run --rm $(APP_SERVICE_NAME) alembic -c $(ALEMBIC_CONFIG_PATH) revision --autogenerate -m "$(m)"

# AANGEPAST: -c vlag toegevoegd.
db-upgrade:
	@echo "Applying all database migrations..."
	docker compose run --rm $(APP_SERVICE_NAME) alembic -c $(ALEMBIC_CONFIG_PATH) upgrade head


# ====================================================================================
# PRODUCTION ENVIRONMENT COMMANDS
# ====================================================================================

production-update:
	@echo "🚀 Starting safe production update..."
	@echo "--> Pulling latest code from branch '$(PULL_BRANCH)'..."
	git pull origin $(PULL_BRANCH)
	@echo "--> Gracefully stopping current running containers (data will be preserved)..."
	docker compose down
	@echo "--> Rebuilding the Docker image with the new code..."
	docker compose build --no-cache
	@echo "--> Starting new containers in the background..."
	docker compose up -d
	@echo "✅ Production update complete. Application is starting with the new version."


.PHONY: help up down logs reset shell db-makemigration db-upgrade production-update