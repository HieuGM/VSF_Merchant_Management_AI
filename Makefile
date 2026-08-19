SHELL := /bin/bash

.PHONY: help install up down clean log logs health restart dev-backend dev-frontend eval

help:
	@echo "Available commands:"
	@echo "  make install       - Install local backend (Python/uv) and frontend (npm) dependencies"
	@echo "  make up            - Start all Docker infrastructure containers in background"
	@echo "  make down          - Stop and remove Docker containers"
	@echo "  make clean         - Stop containers and purge volumes (down -v)"
	@echo "  make log / logs    - Stream live logs from all Docker containers"
	@echo "  make health        - Check health status of Docker containers, Mem0 & Backend"
	@echo "  make restart       - Recreate and restart Mem0 container (apply .env LLM changes)"
	@echo "  make dev-backend   - Run local FastAPI backend dev server"
	@echo "  make dev-frontend  - Run local Vite frontend dev server"
	@echo "  make eval          - Run Tier 1 Planner & Routing evaluation"

install:
	@echo "==> Installing backend dependencies..."
	@cd backend && (uv sync || (.venv/bin/pip install -e . 2>/dev/null || pip install -e .))
	@echo "==> Installing frontend dependencies..."
	@cd frontend && npm install
	@echo "==> Installation complete!"

up:
	@echo "==> Starting Docker containers..."
	docker compose up -d
	@echo "==> Containers started!"

down:
	@echo "==> Stopping Docker containers..."
	docker compose down

clean:
	@echo "==> Stopping Docker containers and removing volumes..."
	docker compose down -v

logs:
	docker compose logs -f

health:
	@echo "=== 1. Docker Container Status ==="
	@docker compose ps
	@echo ""
	@echo "=== 2. Mem0 Health Check ==="
	@curl -s -o /dev/null -w "Mem0 HTTP Status: %{http_code}\n" http://127.0.0.1:8888/api/health || echo "Mem0: Not reachable"
	@echo ""
	@echo "=== 3. Backend Health Check ==="
	@curl -s -o /dev/null -w "Backend HTTP Status: %{http_code}\n" http://127.0.0.1:8000/health || echo "Backend: Not running (start with 'make dev-backend')"

restart:
	@echo "==> Reloading .env and restarting Mem0 container..."
	docker compose up -d --force-recreate mem0
	@echo "==> Mem0 container restarted with latest .env configuration!"

dev-backend:
	@echo "==> Starting FastAPI Backend at http://localhost:8000..."
	@cd backend && LANGFUSE_INSECURE_SSL=true .venv/bin/uvicorn app.main:app --port 8000 --reload

dev-frontend:
	@echo "==> Starting Frontend at http://localhost:5173..."
	@cd frontend && npm run dev

eval:
	@echo "==> Running Tier 1 Routing Evaluation..."
	@cd backend && LANGFUSE_INSECURE_SSL=true .venv/bin/python evals/run_eval.py --tier 1 --label production
