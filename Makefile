.DEFAULT_GOAL := help

# `start` s'appuie sur trap/kill 0 pour arrêter ses trois processus d'un coup :
# on fixe le shell plutôt que de dépendre du /bin/sh de la distribution.
SHELL := /bin/bash

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

# Cibles-fichier d'amorçage : elles permettent à `make start` de fonctionner
# depuis un clone nu, sans enchaîner install / web-install à la main.
.env:
	cp .env.example .env

$(VENV):
	$(MAKE) install

web/node_modules:
	$(MAKE) web-install

.PHONY: start
# Arrêt : `stop` fauche tout le groupe de processus — enfants indirects compris
# (reloader uvicorn, ng serve, esbuild) — en excluant le shell de la recette et
# make lui-même. Un simple `kill 0` tuerait aussi make, qui se plaindrait alors
# en « wait: No child processes » ; et sans le `exit 0` final, make relaierait la
# mort par signal d'onnxruntime en « Segmentation fault » à chaque Ctrl+C.
start: .env $(VENV) web/node_modules ## Lance tout en local : infra Docker + API + worker + web sur la machine (Ctrl+C arrête tout)
	@docker compose up -d --wait
	@echo ""
	@echo "  Web    http://localhost:4200"
	@echo "  API    http://localhost:8000/docs"
	@echo "  MinIO  http://localhost:9001  (minioadmin / minioadmin)"
	@echo ""
	@echo "  Ctrl+C arrête l'API, le worker et le serveur web."
	@echo "  L'infra Docker continue de tourner : 'make down' pour l'arrêter aussi."
	@echo ""
	@PGID=$$(ps -o pgid= -p $$$$ | tr -d ' '); \
	stop() { kill $$(ps -o pid= -g $$PGID | grep -vw -e $$$$ -e $$PPID) 2>/dev/null || true; }; \
	trap 'trap - EXIT; stop; exit 0' EXIT INT TERM; \
	PYTHONUNBUFFERED=1 $(VENV)/bin/uvicorn facereco.interface.api.main:app --reload 2>&1 \
		| sed -u 's/^/[api]    /' & \
	PYTHONUNBUFFERED=1 $(PYTHON) -m facereco.interface.worker.indexing_worker 2>&1 \
		| sed -u 's/^/[worker] /' & \
	(cd web && npm start) 2>&1 | sed -u 's/^/[web]    /' & \
	wait

.PHONY: up
up: ## Démarre l'infra locale (Postgres+pgvector, Redis, MinIO)
	docker compose up -d

# `--profile app` est nécessaire même pour arrêter : sans lui, `down` ignore les
# services de profil et laisserait tourner l'API, le worker et le front.
.PHONY: down
down: ## Arrête tout ce que Docker fait tourner (infra + conteneurs applicatifs)
	docker compose --profile app down

# Postgres n'exécute `/docker-entrypoint-initdb.d` qu'à la CRÉATION du volume :
# une base déjà initialisée ne verra jamais une migration ajoutée depuis. C'est
# la seule façon de la lui appliquer. Les fichiers sont rejouables, la cible
# aussi. Le répertoire `migrations/` est déjà monté dans le conteneur.
.PHONY: migrate
migrate: ## Applique les migrations SQL à la base en cours (idempotent)
	@for f in $$(ls migrations/*.sql | sort); do \
		echo "  -- $$f"; \
		docker compose exec -T -e PGOPTIONS=-cclient_min_messages=warning postgres \
			psql -q -v ON_ERROR_STOP=1 -U facereco -d facereco \
			-f /docker-entrypoint-initdb.d/$$(basename $$f) > /dev/null || exit 1; \
	done
	@echo "  migrations appliquées"

.PHONY: stack
stack: .env ## Lance tout le système en conteneurs (API, worker, web sur :8080) — alternative à `start`
	docker compose --profile app up -d --build
	@echo ""
	@echo "  Web    http://localhost:8080"
	@echo "  API    http://localhost:8000/docs"
	@echo "  MinIO  http://localhost:9001  (minioadmin / minioadmin)"
	@echo ""
	@echo "  Logs : 'make stack-logs' — arrêt : 'make down'"
	@echo ""

.PHONY: stack-logs
stack-logs: ## Suit les logs des conteneurs applicatifs (API, worker, web)
	docker compose --profile app logs -f api worker web

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
import-folder: ## Indexe pour de vrai un dossier local (events/event_images + upload S3 + persistance) : make import-folder FOLDER=chemin [EVENT_ID=1] [TITLE=...] [DESCRIPTION=...] [EVENT_DATE=AAAA-MM-JJ] [ADDRESS=...]
	$(PYTHON) -m facereco.interface.cli.import_folder $(FOLDER) \
		$(if $(EVENT_ID),--event-id $(EVENT_ID)) \
		$(if $(TITLE),--title "$(TITLE)") \
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
