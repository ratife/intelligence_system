.DEFAULT_GOAL := help

VENV   := .venv
PYTHON := $(VENV)/bin/python
PIP    := $(VENV)/bin/pip
FOLDER := /home/eugene/Documents/DOSSIER-TIFE/RCR/IMAGE

TOKEN ?= change-me-in-production

.PHONY: help
help: ## Affiche cette aide
	@grep -E '^[a-zA-Z_-]+:.*?## .*$$' $(MAKEFILE_LIST) | sort \
		| awk 'BEGIN {FS = ":.*?## "}; {printf "  \033[36m%-18s\033[0m %s\n", $$1, $$2}'

.PHONY: install
install: ## Crée le venv, installe les dépendances (dev incluses), prépare .env
	python3 -m venv $(VENV)
	$(PIP) install -e ".[dev]"
	[ -f .env ] || cp .env.example .env

.PHONY: up
up: ## Démarre l'infra locale (Postgres+pgvector, Redis, MinIO)
	docker compose up -d

.PHONY: down
down: ## Arrête l'infra locale
	docker compose down

.PHONY: api
api: ## Lance l'API FastAPI (reload)
	$(VENV)/bin/uvicorn facereco.interface.api.main:app --reload

.PHONY: worker
worker: ## Lance le worker d'indexation (file Redis Streams)
	$(PYTHON) -m facereco.interface.worker.indexing_worker

.PHONY: trigger-indexing
trigger-indexing: ## Publie en file les images en attente d'indexation (TOKEN=... optionnel)
	curl -X POST http://localhost:8000/api/v1/admin/indexing/trigger \
		-H "Authorization: Bearer $(TOKEN)" \
		-H "X-Actor-Id: admin"

.PHONY: index-folder
index-folder: ## Teste détection/qualité/embedding sur un dossier local, sans écriture : make index-folder FOLDER=chemin
	$(PYTHON) -m facereco.interface.cli.index_folder $(FOLDER)

.PHONY: import-folder
import-folder: ## Indexe pour de vrai un dossier local (events/event_images + upload S3 + persistance) : make import-folder FOLDER=chemin [EVENT_ID=1] [DESCRIPTION=...] [EVENT_DATE=AAAA-MM-JJ] [ADDRESS=...]
	$(PYTHON) -m facereco.interface.cli.import_folder $(FOLDER) \
		$(if $(EVENT_ID),--event-id $(EVENT_ID)) \
		$(if $(DESCRIPTION),--description "$(DESCRIPTION)") \
		$(if $(EVENT_DATE),--event-date $(EVENT_DATE)) \
		$(if $(ADDRESS),--address "$(ADDRESS)")

.PHONY: web-install
web-install: ## Installe les dépendances de l'interface web
	cd web && npm install

.PHONY: web
web: ## Lance l'interface web (Angular dev server, http://localhost:4200)
	cd web && npm start

.PHONY: test
test: test-unit ## Alias de test-unit (boucle rapide par défaut)

.PHONY: test-unit
test-unit: ## Tests Domain+Application (rapides, sans dépendance externe)
	$(VENV)/bin/pytest tests/unit -q

.PHONY: test-integration
test-integration: ## Tests Infrastructure (nécessite Docker)
	$(VENV)/bin/pytest tests/integration -m integration -q

.PHONY: test-e2e
test-e2e: ## Tests bout en bout (nécessite Docker)
	$(VENV)/bin/pytest tests/e2e -m e2e -q

.PHONY: lint
lint: ## ruff check
	$(VENV)/bin/ruff check src/ tests/

.PHONY: format
format: ## ruff format (réécrit les fichiers)
	$(VENV)/bin/ruff format src/ tests/

.PHONY: format-check
format-check: ## ruff format --check (non destructif, pour CI)
	$(VENV)/bin/ruff format --check src/ tests/

.PHONY: typecheck
typecheck: ## mypy strict sur src/
	$(VENV)/bin/mypy src/

.PHONY: check
check: lint format-check typecheck test-unit ## Tous les gates rapides (lint+format+types+tests unitaires)

.PHONY: clean
clean: ## Supprime les caches Python et artefacts de build
	rm -rf .mypy_cache .pytest_cache .ruff_cache src/facereco.egg-info
	find . -name '__pycache__' -not -path './.venv/*' -not -path './web/node_modules/*' -exec rm -rf {} +
