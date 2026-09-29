.PHONY: help install install-backend install-frontend backend frontend dev clean \
	lint lint-fix format precommit-install precommit-run \
	docker-build docker-up docker-up-prod docker-down docker-down-prod docker-restart docker-logs docker-ps docker-clean \
	docker-db-shell docker-backend-shell docker-frontend-shell setup-env setup-env-prod migrate-db

# Default target
.PHONY: hrms-up hrms-down hrms-test
hrms-up:
	pwsh -File scripts/hrms-local.ps1 up
hrms-down:
	pwsh -File scripts/hrms-local.ps1 down
hrms-test:
	pwsh -File scripts/hrms-local.ps1 test

help:
	@echo "Available targets:"
	@echo ""
	@echo "Local Development:"
	@echo "  make install          - Install dependencies for both frontend and backend"
	@echo "  make install-backend  - Install Python backend dependencies"
	@echo "  make install-frontend - Install npm frontend dependencies"
	@echo "  make backend          - Start the FastAPI backend server (port 8000)"
	@echo "  make frontend         - Start the Vite frontend dev server"
	@echo "  make dev              - Start both backend and frontend in parallel"
	@echo "  make clean            - Clean build artifacts and cache files"
	@echo ""
	@echo "Code Quality (backend):"
	@echo "  make lint             - Run ruff lint check (no fixes)"
	@echo "  make lint-fix         - Run ruff lint with autofix"
	@echo "  make format           - Run ruff formatter"
	@echo "  make precommit-install - Install git pre-commit hook"
	@echo "  make precommit-run    - Run all pre-commit hooks on all files"
	@echo ""
	@echo "Docker Commands:"
	@echo "  make setup-env        - Create .env file from env.example (first time setup)"
	@echo "  make setup-env-prod   - Create .env.production from env.production.example"
	@echo "  make docker-build     - Build Docker containers"
	@echo "  make docker-up        - Start all Docker containers in background"
	@echo "  make docker-up-prod   - Start production containers using .env.production"
	@echo "  make docker-down      - Stop and remove all Docker containers"
	@echo "  make docker-down-prod - Stop production containers"
	@echo "  make docker-restart   - Restart all Docker containers"
	@echo "  make docker-logs      - View logs from all containers"
	@echo "  make docker-ps        - Show running containers"
	@echo "  make docker-clean     - Remove all containers, volumes, and networks"
	@echo ""
	@echo "Database Commands:"
	@echo "  make migrate-db       - Run database migrations"
	@echo "  make docker-db-shell  - Open PostgreSQL shell in database container"
	@echo ""
	@echo "Shell Access:"
	@echo "  make docker-backend-shell  - Open shell in backend container"
	@echo "  make docker-frontend-shell - Open shell in frontend container"

# Install all dependencies
install: install-backend install-frontend

# Install backend dependencies (uv-managed venv at backend/.venv)
install-backend:
	@command -v uv >/dev/null 2>&1 || { echo "uv not found. Install: curl -LsSf https://astral.sh/uv/install.sh | sh"; exit 1; }
	@echo "Syncing dev tools (ruff, pre-commit, pyright)..."
	cd backend && uv sync --group dev --inexact
	@echo "Installing runtime dependencies from requirements.txt..."
	cd backend && uv pip install -r requirements.txt

# Install frontend dependencies
install-frontend:
	@echo "Installing frontend dependencies..."
	@bash -c 'export NVM_DIR="$$HOME/.nvm" && [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh" && cd frontend && npm install'

# Start PostgreSQL from docker-compose.local
db:
	@echo "Starting PostgreSQL container..."
	@docker compose -f docker-compose.local.yml up -d modular-db
	@echo "Waiting for PostgreSQL to be ready..."
	@until pg_isready -h localhost -p 5455 -q 2>/dev/null; do sleep 0.5; done
	@echo "PostgreSQL ready on port 5455"

# Stop PostgreSQL container
db-stop:
	@echo "Stopping PostgreSQL container..."
	@docker compose -f docker-compose.local.yml down
	@echo "PostgreSQL stopped"

# Start backend server
backend: db
	@echo "Starting backend server on http://localhost:8001"
	@echo "API docs available at http://localhost:8001/docs"
	cd backend && uv run uvicorn main:app --reload --port 8001

# Start frontend server
frontend:
	@echo "Starting frontend dev server..."
	@bash -c 'export NVM_DIR="$$HOME/.nvm" && [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh" && cd frontend && npm run dev'

# Start both servers in parallel
dev: db
	@echo "Starting both backend and frontend servers..."
	@echo "Backend: http://localhost:8001"
	@echo "Frontend: http://localhost:5173"
	@trap 'kill 0' EXIT; \
	(cd backend && uv run uvicorn main:app --reload --port 8001) & \
	(bash -c 'export NVM_DIR="$$HOME/.nvm" && [ -s "$$NVM_DIR/nvm.sh" ] && . "$$NVM_DIR/nvm.sh" && cd frontend && npm run dev') & \
	wait

# Clean build artifacts
clean:
	@echo "Cleaning build artifacts..."
	rm -rf frontend/dist
	rm -rf frontend/node_modules/.vite
	rm -rf backend/__pycache__
	rm -rf backend/app/__pycache__
	rm -rf backend/app/**/__pycache__
	find backend -type d -name __pycache__ -exec rm -r {} + 2>/dev/null || true
	find backend -type f -name "*.pyc" -delete 2>/dev/null || true
	@echo "Clean complete!"

# ============================================================================
# Code Quality (ruff + pre-commit, all run from backend/)
# ============================================================================

# Lint check, no autofix
lint:
	cd backend && uv run ruff check .

# Lint with autofix (safe fixes only)
lint-fix:
	cd backend && uv run ruff check . --fix
	cd backend && uv run ruff format .

# Format only
format:
	cd backend && uv run ruff format .

# Install git pre-commit hook (one-time)
precommit-install:
	cd backend && uv run pre-commit install -c .pre-commit-config.yaml

# Run all pre-commit hooks on every tracked file
precommit-run:
	cd backend && uv run pre-commit run --all-files -c .pre-commit-config.yaml

# ============================================================================
# Docker Commands
# ============================================================================

# Setup environment file
setup-env:
	@if [ ! -f .env ]; then \
		echo "Creating .env file from env.example..."; \
		cp env.example .env; \
		JWT_SECRET=$$(python3 -c "import secrets; print(secrets.token_urlsafe(32))"); \
		if [ "$$(uname)" = "Darwin" ]; then \
			sed -i '' "s#^JWT_SECRET_KEY=.*#JWT_SECRET_KEY=$$JWT_SECRET#" .env; \
		else \
			sed -i "s#^JWT_SECRET_KEY=.*#JWT_SECRET_KEY=$$JWT_SECRET#" .env; \
		fi; \
		echo "✓ .env file created successfully, with a freshly generated JWT_SECRET_KEY!"; \
		echo ""; \
		echo "⚠️  IMPORTANT: Please edit .env and add your API keys:"; \
		echo "   - ANTHROPIC_API_KEY"; \
		echo "   - OPENAI_API_KEY"; \
		echo "   - GOOGLE_CLIENT_ID"; \
		echo "   - GOOGLE_CLIENT_SECRET"; \
	else \
		echo "✓ .env file already exists"; \
	fi

# Setup production environment file
setup-env-prod:
	@if [ ! -f .env.production ]; then \
		echo "Creating .env.production file from env.production.example..."; \
		cp env.production.example .env.production; \
		echo "✓ .env.production file created successfully!"; \
		echo ""; \
		echo "⚠️  IMPORTANT: Please edit .env.production and set:"; \
		echo "   - DATABASE_URL (with SSL)"; \
		echo "   - JWT_SECRET_KEY"; \
		echo "   - ANTHROPIC_API_KEY / OPENAI_API_KEY"; \
	else \
		echo "✓ .env.production file already exists"; \
	fi

# Build Docker containers
docker-build:
	@echo "Building Docker containers..."
	docker compose -f docker-compose.local.yml build

# Start all containers in background
docker-up: setup-env
	@echo "Starting all Docker containers..."
	@echo "This will start:"
	@echo "  - PostgreSQL database on port 5455"
	@echo "  - Backend API on http://localhost:8001"
	@echo "  - Frontend app on http://localhost:5111"
	@echo ""
	docker compose -f docker-compose.local.yml up -d
	@echo ""
	@echo "✓ All services started successfully!"
	@echo ""
	@echo "Access your application:"
	@echo "  Frontend:  http://localhost:5111"
	@echo "  Backend:   http://localhost:8001"
	@echo "  API Docs:  http://localhost:8001/docs"
	@echo ""
	@echo "View logs: make docker-logs"

# Start production containers in background
docker-up-prod: setup-env-prod
	@echo "Starting production Docker containers..."
	docker compose --env-file .env.production -f docker-compose.prod.yml up -d --build
	@echo "✓ Production services started successfully!"

# Stop and remove all containers
docker-down:
	@echo "Stopping all Docker containers..."
	docker compose -f docker-compose.local.yml down
	@echo "✓ All containers stopped"

# Stop production containers
docker-down-prod:
	@echo "Stopping production Docker containers..."
	docker compose --env-file .env.production -f docker-compose.prod.yml down
	@echo "✓ Production containers stopped"

# Restart all containers
docker-restart:
	@echo "Restarting all Docker containers..."
	docker compose -f docker-compose.local.yml restart
	@echo "✓ All containers restarted"

# View logs from all containers
docker-logs:
	docker compose -f docker-compose.local.yml logs -f

# View logs for specific service (usage: make docker-logs-service SERVICE=backend)
docker-logs-service:
	@if [ -z "$(SERVICE)" ]; then \
		echo "Error: SERVICE not specified"; \
		echo "Usage: make docker-logs-service SERVICE=backend|frontend|db"; \
		exit 1; \
	fi
	docker compose -f docker-compose.local.yml logs -f $(SERVICE)

# Show running containers
docker-ps:
	docker compose -f docker-compose.local.yml ps

# Clean up everything (containers, volumes, networks)
docker-clean:
	@echo "⚠️  This will remove all containers, volumes, and networks"
	@echo "Press Ctrl+C to cancel, or Enter to continue..."
	@read -r
	docker compose -f docker-compose.local.yml down -v --remove-orphans
	@echo "✓ All Docker resources cleaned"

# ============================================================================
# Database Commands
# ============================================================================

# Run database migrations
migrate-db:
	@echo "Running database migrations..."
	docker compose -f docker-compose.local.yml exec modular-backend sh -c "cd /app/backend && alembic -c alembic.ini upgrade head"
	@echo "✓ Migrations completed"

# Open PostgreSQL shell
docker-db-shell:
	@echo "Opening PostgreSQL shell..."
	@echo "Connecting to database: statemachine"
	docker compose -f docker-compose.local.yml exec modular-db psql -U statemachine -d statemachine

# ============================================================================
# Container Shell Access
# ============================================================================

# Open shell in backend container
docker-backend-shell:
	@echo "Opening shell in backend container..."
	docker compose -f docker-compose.local.yml exec modular-backend sh

# Open shell in frontend container
docker-frontend-shell:
	@echo "Opening shell in frontend container..."
	docker compose -f docker-compose.local.yml exec modular-frontend sh
