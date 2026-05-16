.PHONY: help install dev ui up up-prod down logs migrate migration test lint format clean docker-build docker-scan

IMAGE_TAG ?= $(shell git rev-parse --short HEAD 2>/dev/null || echo "dev")
IMAGE_REGISTRY ?= ghcr.io/your-org
IMAGE_NAME = chatbot
FULL_IMAGE = $(IMAGE_REGISTRY)/$(IMAGE_NAME):$(IMAGE_TAG)

help:
	@echo "Development:"
	@echo "  make install        - install deps via uv"
	@echo "  make dev            - run FastAPI dev server (port 8000)"
	@echo "  make ui             - run Chainlit UI (port 8501)"
	@echo "  make up             - docker compose up (dev)"
	@echo "  make down           - docker compose down"
	@echo "  make logs           - tail app + worker logs"
	@echo ""
	@echo "Database:"
	@echo "  make migrate        - alembic upgrade head"
	@echo "  make migration MSG='describe' - create new migration"
	@echo ""
	@echo "Testing:"
	@echo "  make test           - pytest"
	@echo "  make lint           - ruff + mypy"
	@echo "  make format         - ruff format + autofix"
	@echo ""
	@echo "Production:"
	@echo "  make docker-build   - build production image"
	@echo "  make docker-scan    - trivy + hadolint scan"
	@echo "  make up-prod        - docker compose up (prod)"

install:
	uv sync --all-extras

dev:
	uv run uvicorn app.main:app --reload --port 8000

ui:
	uv run chainlit run ui/app.py --port 8501

up:
	docker compose up -d

up-prod:
	IMAGE_TAG=$(IMAGE_TAG) docker compose -f docker-compose.prod.yml up -d

down:
	docker compose down

logs:
	docker compose logs -f app worker

migrate:
	uv run alembic upgrade head

migration:
	uv run alembic revision --autogenerate -m "$(MSG)"

test:
	uv run pytest -v

lint:
	uv run ruff check app tests ui
	uv run mypy app

format:
	uv run ruff format app tests ui
	uv run ruff check --fix app tests ui

docker-build:
	docker build \
		-f docker/Dockerfile \
		-t $(FULL_IMAGE) \
		-t $(IMAGE_NAME):latest \
		--target runtime \
		--build-arg GIT_SHA=$(IMAGE_TAG) \
		--build-arg BUILD_DATE=$(shell date -u +%Y-%m-%dT%H:%M:%SZ) \
		.

docker-scan:
	./scripts/security-scan.sh $(IMAGE_NAME):latest

docker-push: docker-build
	docker push $(FULL_IMAGE)

clean:
	find . -type d -name __pycache__ -exec rm -rf {} +
	find . -type f -name "*.pyc" -delete
	rm -rf .pytest_cache .mypy_cache .ruff_cache htmlcov
