# syntax=docker/dockerfile:1

# Image du back : API FastAPI et worker d'indexation partagent le même artefact.
# Les deux processus chargent exactement le même code et les mêmes modèles ONNX
# (le worker duplique le câblage de `deps.py` pour son propre process, cf.
# CLAUDE.md « Composition root ») : deux images divergeraient sur les versions
# de modèle, ce que l'idempotence `(image_id, model_version, face_index)` ne
# pardonnerait pas. Une seule image, deux cibles finales :
#
#   docker build -t facereco-api .                    # cible `api` par défaut
#   docker build -t facereco-worker --target worker .
#
# La configuration passe exclusivement par variables d'environnement : `.env`
# est exclu du contexte (.dockerignore) et `Settings` retombe sur ses défauts,
# qui pointent vers localhost — inutilisables dans un conteneur. Fournir au
# minimum DATABASE_URL, REDIS_URL, S3_ENDPOINT_URL et API_BEARER_TOKEN.

ARG PYTHON_IMAGE=python:3.12-slim-bookworm


# ---------------------------------------------------------------------------
# Étape de build : dépendances + paquet, dans un venv déplaçable tel quel.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS builder

ENV PIP_DISABLE_PIP_VERSION_CHECK=1 \
    PIP_ROOT_USER_ACTION=ignore \
    PATH="/opt/venv/bin:$PATH"

WORKDIR /build

RUN python -m venv /opt/venv

# Les dépendances (onnxruntime, insightface, opencv… ~1 Go) sont installées
# contre un paquet factice réduit à `src/facereco/__init__.py`. Sans cette
# indirection, `pip install .` exigerait le code source complet et la moindre
# modification d'un fichier Python invaliderait le cache de toute la couche.
COPY pyproject.toml ./
RUN --mount=type=cache,target=/root/.cache/pip \
    mkdir -p src/facereco && touch src/facereco/__init__.py \
    && pip install . \
    && pip uninstall --yes facereco

COPY src/ src/
RUN --mount=type=cache,target=/root/.cache/pip pip install --no-deps .

# Poids buffalo_l (~280 Mo) embarqués dans l'image plutôt que téléchargés au
# premier appel : le `lifespan` de l'API construit détecteur et embedder au
# démarrage, un conteneur neuf resterait donc plusieurs minutes sans répondre,
# et échouerait tout court sur un réseau fermé. `--build-arg PREFETCH_MODELS=false`
# rend la main au téléchargement à chaud si le contexte de build est hors ligne.
ARG PREFETCH_MODELS=true
ARG INSIGHTFACE_MODEL_PACK=buffalo_l
RUN mkdir -p /opt/insightface \
    && if [ "$PREFETCH_MODELS" = "true" ]; then \
         python -c "from insightface.utils import ensure_available; \
ensure_available('models', '${INSIGHTFACE_MODEL_PACK}', root='/opt/insightface')"; \
       fi


# ---------------------------------------------------------------------------
# Base d'exécution commune à l'API et au worker.
# ---------------------------------------------------------------------------
FROM ${PYTHON_IMAGE} AS runtime

# libGL/libglib : `insightface` dépend d'`opencv-python` (build complet, pas
# seulement le headless déclaré dans pyproject.toml) — sans elles, `import cv2`
# échoue sur libGL.so.1. libgomp : OpenMP, requis par onnxruntime.
RUN apt-get update \
    && apt-get install --yes --no-install-recommends \
        libgl1 \
        libglib2.0-0 \
        libgomp1 \
    && rm -rf /var/lib/apt/lists/*

ENV PATH="/opt/venv/bin:$PATH" \
    PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1

# Utilisateur non privilégié : le service traite des images fournies par
# l'extérieur, il n'a aucune raison de tourner en root.
RUN useradd --create-home --uid 1000 facereco

COPY --from=builder /opt/venv /opt/venv
# `model_registry.load_model_by_taskname` résout les poids sous `~/.insightface`
# (chemin non configurable côté code) : c'est donc le HOME de l'utilisateur qui
# fixe l'emplacement. Monter un volume nommé ici reste possible et sain — Docker
# l'initialise avec le contenu de l'image, API et worker partagent alors le cache.
COPY --from=builder --chown=facereco:facereco /opt/insightface /home/facereco/.insightface

WORKDIR /app
USER facereco


# ---------------------------------------------------------------------------
# Worker d'indexation — consommateur Redis Streams, aucun port exposé.
# ---------------------------------------------------------------------------
FROM runtime AS worker

# Chaque process dérive son propre nom de consommateur `<host>-<pid>` : deux
# réplicas ne se voleront pas leurs messages en vol via XAUTOCLAIM.
CMD ["python", "-m", "facereco.interface.worker.indexing_worker"]


# ---------------------------------------------------------------------------
# API FastAPI — cible par défaut.
# ---------------------------------------------------------------------------
FROM runtime AS api

EXPOSE 8000

# Pas d'endpoint /health dédié dans l'application : /openapi.json est servi par
# FastAPI lui-même et ne devient disponible qu'une fois le `lifespan` terminé,
# donc modèles ONNX chargés — exactement le signal recherché. `start-period`
# couvre ce chargement (plus long encore si les poids ne sont pas préembarqués).
HEALTHCHECK --interval=30s --timeout=5s --start-period=120s --retries=3 \
    CMD python -c "import urllib.request; urllib.request.urlopen('http://127.0.0.1:8000/openapi.json', timeout=3)"

# Pas de `--reload` ici (il double la mémoire et recharge les modèles à chaud) ;
# pas de `--workers` non plus : chaque worker uvicorn instancierait sa propre
# paire détecteur/embedder ONNX. La montée en charge passe par des réplicas.
CMD ["uvicorn", "facereco.interface.api.main:app", "--host", "0.0.0.0", "--port", "8000"]
