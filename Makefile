# Makefile for managing Docker Compose application

# Stop and remove containers, networks, volumes, and images created by 'up'.
# Then, build services without using cache.
# Finally, create and start containers in detached mode.
reset:
	docker compose down -v
	docker compose build --no-cache
	docker compose up -d

# Build or rebuild services
build:
	docker compose build

# Create and start containers in detached mode
up:
	docker compose up -d

# Follow log output with details for the apigen_app service
log:
	docker logs --details apigen_app

# Phony targets are not files
.PHONY: reset build up log