.PHONY: setup start stop logs reset status

# Copy environment template
setup:
	@if [ ! -f .env ]; then \
		cp .env.example .env; \
		echo ".env created from template. Configure settings as needed."; \
	else \
		echo ".env file already exists. Skipping copy."; \
	fi

# Start all Docker services in background
start:
	docker compose up --build -d

# Stop all services and network
stop:
	docker compose down

# Follow log trace streams
logs:
	docker compose logs -f

# Check container status
status:
	docker compose ps

# Reset stack, tear down volumes and data storage caches
reset:
	docker compose down -v
	@echo "All services terminated and local data volumes purged."
