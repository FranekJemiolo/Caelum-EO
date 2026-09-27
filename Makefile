# Caelum-EO — Developer Makefile
# Requires: uv >= 0.4  (https://docs.astral.sh/uv/)

.PHONY: help install install-ml sync lock lint fmt typecheck test test-cov \
        pre-commit clean dev docker-up docker-down

# ── colours ─────────────────────────────────────────────────────────────────
BOLD  := $(shell tput bold 2>/dev/null || echo "")
RESET := $(shell tput sgr0 2>/dev/null || echo "")

help: ## Show this help
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | \
	  awk 'BEGIN {FS = ":.*?## "}; {printf "  $(BOLD)%-18s$(RESET) %s\n", $$1, $$2}'

# ── Setup ────────────────────────────────────────────────────────────────────
install: ## Create .venv and install core + dev deps
	uv sync --extra dev

install-ml: ## Add ML extras (torch / torchvision) on top of dev install
	uv sync --extra dev --extra ml

sync: ## Re-sync .venv to lockfile (use after pulling)
	uv sync --extra dev

lock: ## Re-generate uv.lock from pyproject.toml
	uv lock

# ── Quality Gates ────────────────────────────────────────────────────────────
lint: ## Run ruff linter
	uv run ruff check src/ tests/

fmt: ## Run ruff formatter
	uv run ruff format src/ tests/

fmt-check: ## Check formatting without modifying files (CI-safe)
	uv run ruff format --check src/ tests/

typecheck: ## Run mypy type checker
	uv run mypy src/ --ignore-missing-imports

pre-commit: ## Run all pre-commit hooks against all files
	uv run pre-commit run --all-files

# ── Testing ──────────────────────────────────────────────────────────────────
test: ## Run the full test suite
	uv run pytest tests/ -v

test-cov: ## Run tests with HTML coverage report (opens in browser)
	uv run pytest tests/ \
	  --cov=src \
	  --cov-report=term-missing \
	  --cov-report=html:htmlcov \
	  --cov-fail-under=80
	@echo "Coverage report: htmlcov/index.html"

# ── Docker ───────────────────────────────────────────────────────────────────
docker-up: ## Bring up the full local stack (PostGIS, MinIO, API, frontend)
	docker compose up --build -d

docker-down: ## Tear down the local stack
	docker compose down -v

# ── Housekeeping ─────────────────────────────────────────────────────────────
clean: ## Remove build artefacts and caches
	rm -rf .venv htmlcov .coverage dist build *.egg-info
	find . -type d -name __pycache__ -exec rm -rf {} + 2>/dev/null; true
	find . -type f -name "*.pyc" -delete
