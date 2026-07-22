# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project

Événement facial recognition system (`facereco`): automatic face indexing on
images belonging to a pre-existing events system, and reverse search ("which
events does this person appear in, given a photo"). Implements Clean
Architecture (Uncle Bob) in Python/FastAPI, per the technical scoping document
`Analyse-Technique-Reconnaissance-Faciale.pdf` (v1.0) — that PDF is the source
of truth for requirements; code comments reference it by section (`§7.1`) and
by ADR/requirement IDs (`ADR 006`, `P4`, etc.).

Only Lot 1 (indexing) and Lot 2 (search) are implemented end-to-end. Lot 3
(observability, automated GDPR purge) and Lot 4 (identity clustering) have
domain-level extension points only (e.g. `person_clusters.purge_after` column
exists but is unused) — deliberately not implemented to avoid locking in an
architecture that would need undoing. Legal scoping (Lot 0: legal basis,
consent, DPIA) is a blocking prerequisite for real data and is out of scope
for this repo — dev/tests use public/synthetic data only.

## Commands

Most commands below have a `make` equivalent (`make help` lists them all) —
same commands, shorter to type.

```bash
# Install
python3 -m venv .venv && source .venv/bin/activate
pip install -e ".[dev]"
cp .env.example .env

# Local infra (Postgres+pgvector, Redis, MinIO)
docker compose up -d

# Run API (downloads InsightFace buffalo_l weights on first call, ~280MB)
uvicorn facereco.interface.api.main:app --reload

# Run indexing worker (consumes Redis Streams queue)
python -m facereco.interface.worker.indexing_worker

# Dev-only: test detection/quality/embedding on a local folder of images,
# no DB/Redis/S3, no Event required (see interface/cli/index_folder.py)
python -m facereco.interface.cli.index_folder /path/to/folder

# Dev-only: actually index a local folder — creates events/event_images,
# uploads to S3/MinIO, persists embeddings (see interface/cli/import_folder.py)
python -m facereco.interface.cli.import_folder /path/to/folder [--event-id N]

# Web UI (Angular, standalone components) — search-by-face frontend, web/
cd web && npm install && npm start   # http://localhost:4200, API must be on :8000

# Tests — three tiers, run independently
pytest tests/unit -q                        # Domain+Application, no external deps, <1s
pytest tests/integration -m integration -q  # Infrastructure adapters, needs Docker (testcontainers)
pytest tests/e2e -m e2e -q                  # Full FastAPI app, ML adapters replaced by fakes, needs Docker

# Single test
pytest tests/unit/domain/test_event_scoring.py::test_name -q

# Quality gates (mirror what CI expects)
ruff check src/ tests/
ruff format --check src/ tests/
mypy src/
```

`mypy` runs in `strict = true` mode against `src/` only (tests excluded).
`ruff` line length is 100; enabled rule sets are `E, F, I, UP, B, SIM`.

## Architecture

Strict four-layer Clean Architecture under `src/facereco/`:

```
domain/          entities, value objects, pure business rules, ports (interfaces)
application/     use cases — orchestration through domain ports only
infrastructure/  Postgres/pgvector, Redis Streams, InsightFace/ONNX Runtime, S3/MinIO
interface/       FastAPI routers/schemas + the indexing worker entrypoint
```

**Dependency rule is load-bearing and checked by grep, not just convention:**
`domain/` must never import `fastapi`, `sqlalchemy`, `onnxruntime`, `redis`, or
`boto3` — verify with `grep -r "fastapi\|sqlalchemy\|onnxruntime\|redis\|boto3" src/facereco/domain/`
(must return empty) before considering any domain-layer change done.
`application/` depends only on `domain/` ports. `infrastructure/` implements
those ports. `interface/api/deps.py` is the **composition root** — the only
place that knows both use cases and concrete adapter implementations.

### Ports (`domain/ports/`) — the seam infrastructure must respect

Every external dependency is behind an ABC port: `FaceDetectorPort`,
`FaceEmbedderPort`, `FaceEmbeddingRepositoryPort`, `EventRepositoryPort`,
`VectorSearchPort`, `MessageQueuePort`, `ObjectStoragePort`, `SearchQuotaPort`,
`AuditLogPort`, `ClockPort`. Two invariants are easy to violate accidentally
when touching detection/embedding code:

- **`FaceDetectorPort` and `FaceEmbedderPort` are shared verbatim between the
  indexing pipeline and the search pipeline.** Any divergence in
  pre/post-processing between the two call sites silently destroys matching
  accuracy — this is called out in the source doc as "piège classique n°1".
  Don't create a second detector/embedder instantiation path for search.
- **`EmbeddingVector` is always L2-normalized** (`domain/value_objects/embedding_vector.py`
  enforces this in `__post_init__` and raises if not ≈1.0 norm). This is what
  makes cosine similarity reduce to a dot product and lets pgvector's HNSW
  index work. Never construct one from a raw un-normalized vector directly —
  use `EmbeddingVector.from_raw`.

### Idempotency and quality gating (worker path)

- `FaceEmbedding.idempotency_key()` = `(image_id, model_version, face_index)`,
  enforced as a DB unique constraint (`migrations/0001_init.sql`). Replaying
  the same queue message must never create duplicate vectors.
- Faces failing quality gates (`domain/value_objects/quality.py`,
  `assess_face_quality`) are **never silently dropped** — they're persisted to
  `rejected_faces` with a reason string, to make rejection rate measurable and
  thresholds tunable later.
- The message queue models consumer groups, explicit ACK, and dead-letter
  after `INDEXING_MAX_DELIVERY_ATTEMPTS` retries (`MessageQueuePort`) so a
  single corrupt image can't block the batch indefinitely.

### Search pipeline (`application/use_cases/search_by_face.py`)

Sequence: quota check → detect faces in query image → resolve which face to
use → embed → ANN top-K via `VectorSearchPort` → threshold → aggregate by
event (`domain/services/event_scoring.py`) → audit log → return with evidence.

- If more than one face is detected and the caller didn't pass `face_index`,
  the use case raises `AmbiguousFaceSelectionError` rather than guessing —
  callers must disambiguate explicitly.
- Event aggregation score = `max(similarity) + λ·log(1 + match_count)`
  (`DEFAULT_CORROBORATION_LAMBDA = 0.02`). Max alone is too sensitive to a
  single false positive; averaging dilutes the signal on high-face-count
  events. Don't replace this with a plain average or max without re-reading
  `event_scoring.py`'s docstring rationale.
- Every match is returned with a `FaceEvidence` (source image + bbox) — the
  system never surfaces a bare similarity score, so a human can verify a hit.
  Preserve this pairing in any API/schema change.
- `AuditLogPort.record_search` stores a SHA-256 hash of the query image, never
  the image itself — this is a non-negotiable compliance requirement (ADR
  008), not an optimization.

### Domain exceptions → HTTP mapping

`domain/exceptions.py` defines a `DomainError` hierarchy with zero HTTP
knowledge. `interface/api/error_handlers.py` is the only place allowed to
translate exception types to status codes (409 no-face/ambiguous, 422
invalid-face-index/quality-rejected, 404 event-not-found, 429 quota, 400
generic `DomainError` fallback). Adding a new domain exception means adding a
row to `_STATUS_BY_EXCEPTION` there, not raising `HTTPException` from
use cases or domain code.

### Composition root and heavy adapters

`interface/api/deps.py` wires ports to concrete adapters via FastAPI
`Depends`. ONNX models (detector, embedder) are expensive to load, so they're
instantiated once in `main.py`'s `lifespan` and reused via `request.app.state`
— never reconstructed per-request. The standalone worker
(`interface/worker/indexing_worker.py`) duplicates this same wiring for its
own process rather than importing from the API app, since it runs
independently.

### Auth (MVP-level, intentionally simplified)

A single shared bearer token (`API_BEARER_TOKEN`) plus a required
`X-Actor-Id` header (used for quota + audit identification), checked in
`get_current_actor_id` (`interface/api/deps.py`). This is explicitly flagged
in the README as needing replacement by a real IAM before production (§13).
Don't over-engineer auth changes here without checking whether the ask is
actually about the IAM migration.

### Web frontend (`web/`)

A separate Angular workspace (standalone components, no NgModules — scaffolded
with Angular CLI 21, 2025 file-naming style: `search.ts`/`.html`/`.css`, no
`.component.` infix). It's a thin client for `POST /api/v1/search/by-face`
only — no indexing UI. `src/app/models/search.model.ts` mirrors
`interface/api/schemas/search.py`'s Pydantic schemas field-for-field; if that
schema changes, update the TS interfaces by hand (no codegen wired up).
Auth (bearer token + actor id) is entered in the UI and persisted to
`localStorage`, matching the backend's MVP-level shared-token auth — see
"Auth" above. The FastAPI app has `CORSMiddleware` configured via
`settings.cors_allowed_origins` (defaults to `http://localhost:4200`)
specifically so this dev server can call it; keep that setting in sync if the
frontend's origin/port changes.

## Testing conventions

- `tests/unit`: pure Domain/Application, fakes only (see
  `tests/unit/application/fakes.py` for `ScriptedFaceDetector`,
  `DeterministicFaceEmbedder` etc.), no Docker required.
- `tests/integration`: real adapters against `testcontainers` Postgres+pgvector
  and Redis (`tests/integration/infrastructure/conftest.py`). Schema is
  (re)applied per test module from `migrations/0001_init.sql`; tables are
  truncated after each test.
- `tests/e2e`: full FastAPI app wired through `TestClient`, real Postgres via
  testcontainers, but ML/queue/storage adapters swapped for deterministic
  fakes/in-memory implementations (`tests/e2e/conftest.py`) — pgvector itself
  is exercised because aggregation/thresholding behavior is part of the
  contract under test.
- Known non-goals to keep in mind before "fixing" them as bugs: fixed 5s retry
  backoff in `RedisStreamsQueue` (not exponential), yaw/pose estimated by a
  cheap landmark heuristic (not a 3D pose model), similarity threshold (0.38)
  is an uncalibrated default pending real-data calibration — all documented
  in the README's "Limites connues de ce MVP".
