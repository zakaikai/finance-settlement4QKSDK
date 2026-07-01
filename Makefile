# Financial Settlement System — Makefile
# Targets for setup, development, testing, and building.
# Usage:
#   make setup       # One-time setup (venv + npm install)
#   make dev-backend # Start backend with auto-reload
#   make dev-frontend# Start frontend with hot-reload
#   make build       # Build frontend for production
#   make test        # Run Python tests
#   make lint        # Lint Python code
#   make clean       # Remove build artifacts

.PHONY: setup dev-backend dev-frontend build test lint clean

VENV = backend/.venv
PYTHON = $(VENV)/bin/python
PIP = $(VENV)/bin/pip
# Windows: override at invocation: make PYTHON=backend\.venv\Scripts\python

# ── Setup ──

setup: $(VENV)/bin/python frontend/node_modules

$(VENV)/bin/python:
	python3 -m venv $(VENV)
	$(PIP) install -r backend/requirements.txt
	$(PIP) install -r backend/requirements-dev.txt

frontend/node_modules:
	cd frontend && npm install

# ── Development ──

dev-backend:
	$(VENV)/bin/uvicorn backend.main:app --reload --port 8770

dev-frontend:
	cd frontend && npx vite --port 5173

# ── Build ──

build:
	cd frontend && npx vite build

build-package: build
	$(PIP) install pyinstaller
	pyinstaller FinanceSettlement.spec --clean --noconfirm
	cp version.json dist/FinanceSettlement/

# ── Testing ──

test:
	$(VENV)/bin/pytest backend/tests/ -v

test-coverage:
	$(VENV)/bin/pytest backend/tests/ --cov=backend --cov-report=term

# ── Lint ──

lint:
	$(VENV)/bin/ruff check backend/

lint-fix:
	$(VENV)/bin/ruff check --fix backend/

# ── Clean ──

clean:
	rm -rf build/ dist/ *.spec
	rm -rf frontend/dist/
	rm -rf .pytest_cache/ .ruff_cache/
	rm -rf backend/.venv/ frontend/node_modules/
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null || true
	find . -type f -name "*.pyc" -delete 2>/dev/null || true
