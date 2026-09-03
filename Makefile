# Bhao Makefile — C owns; A and B request targets via STATUS.md
PY ?= .venv/Scripts/python   # Windows/Git Bash venv path; override with PY=python3 on *nix
PIP ?= .venv/Scripts/pip

.PHONY: help install test lint fmt fixtures weekly backfill api web docker-up spike

help:
	@echo "Bhao targets:"
	@echo "  install      create venv deps (requires python3.11)"
	@echo "  test         run the full pytest suite"
	@echo "  lint         ruff check"
	@echo "  fmt          ruff + black formatting"
	@echo "  fixtures     regenerate contracts/fixtures (deterministic)"
	@echo "  spike        A's data-source verification spike (network)"
	@echo "  weekly       full pipeline: scrape -> validate -> publish -> score -> drift -> forecast"
	@echo "  backfill     one-off Wayback CDX historical backfill"
	@echo "  api          run the FastAPI server on :8000"
	@echo "  web          run the Next.js dev server on :3000"
	@echo "  docker-up    docker compose up (api + web + data volume)"

install:
	py -3.11 -m venv .venv || python3.11 -m venv .venv || true
	$(PIP) install --upgrade pip
	$(PIP) install -e ".[dev]"
	$(PY) -m pre_commit install || true

test:
	$(PY) -m pytest tests -q

lint:
	$(PY) -m ruff check contracts ingest orchestration features models evaluation drift registry api ops tests
	$(PY) -m black --check -q contracts ingest orchestration features models evaluation drift registry api ops tests || true

fmt:
	$(PY) -m ruff check --fix -q contracts ingest orchestration features models evaluation drift registry api ops tests
	$(PY) -m black -q contracts ingest orchestration features models evaluation drift registry api ops tests

fixtures:
	$(PY) -m contracts.fixtures.make_fixtures

spike:
	$(PY) -m ingest.spike

weekly:
	$(PY) -m orchestration.weekly

backfill:
	$(PY) -m orchestration.backfill

api:
	$(PY) -m uvicorn api.main:app --reload --port 8000

web:
	cd web && npm run dev

docker-up:
	docker compose -f docker/compose.yml up --build
