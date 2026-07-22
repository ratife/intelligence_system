# Système de reconnaissance faciale événementielle

Indexation automatique des visages présents dans les images d'un système
d'événements existant, et recherche des événements où une personne apparaît à
partir d'une photo. Implémentation Clean Architecture (Uncle Bob) en Python /
FastAPI, conforme au cadrage technique CTO (`Analyse-Technique-Reconnaissance-Faciale.pdf`, v1.0).

## Périmètre de cette implémentation

- **Lot 1 (indexation) + Lot 2 (recherche)** implémentés de bout en bout.
- **Lot 3 (observabilité avancée, purge RGPD automatisée)** et **Lot 4
  (clustering d'identités)** : ports et points d'extension prévus dans le
  Domain, non implémentés — pour ne pas figer une architecture qu'il faudrait
  ensuite défaire.
- Développement et tests sur données publiques/synthétiques uniquement. **Le
  Lot 0 (cadrage juridique : base légale, consentement, DPIA) est un
  prérequis bloquant à tout traitement de données réelles** (§3 et §16 du
  cadrage technique) — il est hors périmètre de ce dépôt.

## Architecture

```
Domain            → entités, value objects, règles métier pures, ports (interfaces)
Application       → use cases, orchestration via les ports du Domain
Infrastructure    → PostgreSQL/pgvector, Redis Streams, InsightFace/ONNX Runtime, S3/MinIO
Interface         → API FastAPI (routers, schemas HTTP) + worker de consommation
```

Règle de dépendance : `Domain` ne dépend d'aucune couche externe (vérifiable
par `grep -r "fastapi\|sqlalchemy\|onnxruntime\|redis\|boto3" src/facereco/domain/`,
qui doit retourner vide). `Application` ne dépend que des ports du `Domain`.
`Infrastructure` implémente ces ports. `Interface` assemble le tout
(composition root dans `interface/api/deps.py`).

Détail de l'arborescence : voir `src/facereco/`.

Une interface Angular minimale (`web/`) consomme cette API pour la recherche
par visage — voir "Lancer l'interface web" ci-dessous.

Toutes les commandes de ce README sont aussi disponibles via `make` (`make
help` pour la liste) — installation, infra, API, worker, web, tests, qualité.

## Prérequis

- Python 3.11+
- Docker + Docker Compose (PostgreSQL+pgvector, Redis, MinIO)
- ~2 Go d'espace disque et un accès réseau au premier lancement (téléchargement
  des poids InsightFace `buffalo_l` : détection SCRFD + embedding ArcFace R100)

## Installation

```bash
python3 -m venv .venv
source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env
```

## Lancer l'infrastructure locale

```bash
docker compose up -d
```

Démarre PostgreSQL+pgvector (schéma appliqué automatiquement via
`migrations/0001_init.sql`), Redis et MinIO. Créer le bucket S3/MinIO utilisé
par défaut (`facereco-events`) via la console MinIO (http://localhost:9001,
identifiants `minioadmin` / `minioadmin`) ou l'AWS CLI :

```bash
aws --endpoint-url http://localhost:9000 s3 mb s3://facereco-events
```

## Lancer l'API

```bash
uvicorn facereco.interface.api.main:app --reload
```

Le premier démarrage télécharge les modèles InsightFace (`~/.insightface/models/buffalo_l`,
~280 Mo) — attendre la fin du téléchargement avant le premier appel. Documentation
interactive : http://localhost:8000/docs.

## Lancer le worker d'indexation

```bash
python -m facereco.interface.worker.indexing_worker
```

Consomme la file Redis Streams (`facereco:indexing`), traite les images
(détection → filtre qualité → embedding → persistance idempotente), avec
reprise sur erreur et bascule en dead-letter queue après échec répété.

## Tester le pipeline d'indexation sur un dossier local

```bash
python -m facereco.interface.cli.index_folder /chemin/vers/dossier
```

Exécute détection → filtre qualité → embedding sur toutes les images d'un
dossier local, avec les mêmes adapters ML que la production — sans base de
données, sans file Redis, sans rattachement à un `Event`. Utile pour valider
rapidement le comportement de détection/qualité sur des images arbitraires
avant de les faire transiter par le pipeline complet (worker + Postgres).

## Indexer pour de vrai un dossier local

```bash
python -m facereco.interface.cli.import_folder /chemin/vers/dossier
# ou en rattachant à un événement existant :
python -m facereco.interface.cli.import_folder /chemin/vers/dossier --event-id 1
```

Contrairement à l'outil de test ci-dessus, celui-ci **persiste réellement** :
il crée les lignes `events`/`event_images` (un nouvel événement si
`--event-id` n'est pas fourni — `--description`/`--event-date`/`--address`
pour le personnaliser), upload chaque image dans MinIO/S3, puis exécute le
pipeline d'indexation complet (comme le worker de production). Les
empreintes deviennent immédiatement cherchables via `/api/v1/search/by-face`
ou l'interface web. Idempotent : une image déjà importée (même contenu) est
ignorée, pas dupliquée. Pratique pour peupler un environnement de dev/démo
sans dépendre du système d'événements pré-existant (hors périmètre en
production, cf. "Périmètre de cette implémentation" ci-dessus).

## Déclencher une indexation

```bash
curl -X POST http://localhost:8000/api/v1/admin/indexing/trigger \
  -H "Authorization: Bearer change-me-in-production" \
  -H "X-Actor-Id: admin"
```

Publie en file tous les `event_images` en attente d'indexation pour la
version de modèle courante (backfill + incrémental confondus). Le worker doit
tourner en parallèle pour les traiter.

## Lancer l'interface web

```bash
cd web
npm install
npm start
```

Sert l'interface de recherche par visage sur http://localhost:4200 (Angular,
composants standalone). L'API doit tourner sur http://localhost:8000
(`CORS_ALLOWED_ORIGINS` autorise `http://localhost:4200` par défaut). Le
formulaire demande le jeton `Bearer` et l'`X-Actor-Id` (mêmes valeurs que pour
l'API, persistées en `localStorage` du navigateur) puis affiche les
événements retrouvés avec leur preuve (image + score de confiance).

## Rechercher par visage

```bash
curl -X POST http://localhost:8000/api/v1/search/by-face \
  -H "Authorization: Bearer change-me-in-production" \
  -H "X-Actor-Id: alice" \
  -F "image=@photo.jpg" \
  -F "limit=20"
```

Réponse : liste des événements classés par confiance décroissante, chacun
accompagné d'une preuve (image + zone de visage). Codes d'erreur : `409` (aucun
visage détecté, ou plusieurs sans `face_index`), `422` (`face_index` invalide),
`413` (image > 10 Mo), `429` (quota de recherche dépassé).

> Authentification simplifiée pour ce MVP : un jeton `Bearer` partagé
> (`API_BEARER_TOKEN`) plus un en-tête `X-Actor-Id` identifiant l'appelant
> (utilisé pour le quota et le journal d'audit). À remplacer par un IAM complet
> avant mise en production (§13 du cadrage technique).

## Tests

```bash
# Domain + Application — aucune dépendance externe, s'exécute en < 1s
pytest tests/unit -q

# Infrastructure — nécessite Docker (testcontainers Postgres + Redis)
pytest tests/integration -m integration -q

# Bout en bout — nécessite Docker (adapters ML remplacés par des fakes déterministes)
pytest tests/e2e -m e2e -q

# Qualité
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
```

## Limites connues de ce MVP

- **Lot 3 non implémenté** : pas de métriques Prometheus, pas de procédure de
  purge RGPD automatisée (le port `person_clusters.purge_after` existe en
  base mais n'est pas exploité), pas de back-office de modération.
- **Lot 4 non implémenté** : pas de clustering d'identités (HDBSCAN) —
  chaque recherche compare le visage requête à l'ensemble de l'index, sans
  passer par des centroïdes de clusters.
- **Backoff de retry simplifié** : un plancher fixe de 5 s avant reprise
  (`RedisStreamsQueue`), pas une exponentielle par tentative.
- **Yaw (pose) approximatif** : estimé par une heuristique géométrique légère
  sur les 5 points de repère, pas par un modèle de pose 3D dédié.
- **Authentification simplifiée** : jeton statique partagé, pas d'IAM par
  acteur — voir §13 du cadrage technique pour l'exigence cible.
- **Seuil de similarité non calibré** : la valeur par défaut (0,38) est celle
  du cadrage technique (« équilibré ») ; le §10.2 impose une calibration sur
  données réelles avant mise en production, hors périmètre de ce dépôt.
