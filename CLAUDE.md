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
- **`EventRepositoryPort`/`ObjectStoragePort` deliberately have no create
  methods** — in production `events`/`event_images` and the object storage
  are populated by the pre-existing external events system (§2.1), not by
  this service. The dev/demo paths that need to create data anyway
  (`interface/cli/import_folder.py`, `interface/api/routers/admin_events.py`)
  go through `infrastructure/devtools/event_import.py`, which bypasses the
  ports on purpose (direct ORM + boto3) — don't "fix" this by adding create
  methods to the ports; that would blur a real architectural boundary for
  the sake of tooling that isn't a production use case.

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
  callers must disambiguate explicitly. `POST /api/v1/search/faces`
  (`DetectQueryFacesUseCase`) is what makes that demand answerable: it returns
  every detected face's bbox and index so a caller can *see* what index 2 is
  before naming it. It deliberately stays out of the search pipeline — no
  quota (nothing is queried, and spending the operator's search budget just to
  draw boxes would be wrong), no audit entry (ADR 008 covers searches, not
  detections), no quality gate (that gate is an indexing rule; showing a
  « rejected » verdict here would imply a barrier search doesn't have). It uses
  the same shared `FaceDetectorPort`, so the boxes shown are the ones search
  will use — an image with no face returns an empty list rather than 409,
  since « what is in this image » has « nothing » as a valid answer.
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
`.component.` infix). Three tabs, toggled in `app.ts` via a plain signal (no
Angular Router — `ng new` was run with `--routing=false`): **Tableau de bord**
(`dashboard/`, `GET /api/v1/stats` — the default tab), **Recherche**
(`search/`, `POST /api/v1/search/faces` then `POST /api/v1/search/by-face`)
and **Importer un événement**
(`event-import/`, the `admin_events` routes below). `src/app/models/*.model.ts`
mirror the backend's Pydantic schemas field-for-field by hand (no codegen
wired up) — update both sides together when a schema changes. The FastAPI app
has `CORSMiddleware` configured via
`settings.cors_allowed_origins` (defaults to `http://localhost:4200`)
specifically so this dev server can call it; keep that setting in sync if the
frontend's origin/port changes.

**Faces are shown, never just numbered or scored.** Two presentational
components carry this, both under `web/src/app/`:

- `face-frame/` — an image plus its face boxes. Boxes arrive in *image pixels*
  and are converted to percentages of the natural dimensions, so they survive
  any display size. Two things it must keep doing: its wrapper is
  `inline-block` so it hugs the image exactly (letterboxing would shift every
  box), and each measurement is stored **with the `src` that produced it**, so
  switching photos can't paint new boxes onto the previous image's dimensions.
  No EXIF correction is applied or needed — OpenCV (detection side, verified on
  cv2 5.0) and browsers both apply EXIF orientation, so the two coordinate
  frames already agree. Note `_image_size()` in `devtools/event_import.py` does
  *not*: it reads PIL's raw size, so `event_images.width/height` is wrong for
  rotated photos — don't build overlays on those columns.
- `face-crop/` — a square close-up on one face, done by scaling and offsetting
  the same (already cached) image inside a fixed window, no server-side crop.
  It exists because a 150px face in a 4000px photo renders ~10px wide in a card:
  the frame answers *where*, the crop answers *who*, and only the second makes
  a similarity score checkable by a human.

`search/` uses both. Picking a file triggers detection immediately, so the
photo comes back with every face framed; with more than one face the operator
**clicks** the one to search (the old free-text "Index de visage" field is
gone — it asked for a number nothing on screen explained, and a group photo
was otherwise a dead end at 409). Badges read `#0`, `#1` — the API's own
`face_index`, with `#` marking it as an identifier rather than a rank; don't
renumber them 1-based, the audit log and the API speak the 0-based one.
Changing the selected face clears the previous results, which described a
different person. If detection is unreachable the search stays available (the
API will arbitrate) and the used face is still framed afterwards from
`query.face_used`.

**Styling goes through a shared design system, not per-component CSS.**
`web/src/styles.css` holds the design tokens (surfaces, one ink per role,
accent, status colors, radii, spacing scale, shadows, a single focus ring) and
the app-level primitives: `.page`/`.subtitle`/`.micro-label`, `.card`,
`.btn` + `.btn--primary`/`.btn--quiet`/`.btn--sm`, `.alert--error`/`.alert--info`,
the form control base styles, and the shared data-viz pieces used by both the
dashboard and the import progress panel (`.meter`, `.stack`/`.legend`/`.swatch`
+ `.tone-*`, `.tiles`/`.tile`). These are deliberately **global**: Angular's
view encapsulation only scopes styles written inside a component, so a global
base is what lets one system reach every screen. A component's own `.css` keeps
only what is genuinely local to it — no colors in hex, no re-declared page
shell, card or button. Before adding a rule, check whether the token or
primitive already exists; before hardcoding a color, add or reuse a token.
`grep -n "#[0-9a-fA-F]\{3,6\}" web/src/app/*/*.css` must stay empty.

**The whole UI sits behind a login gate.** `app.html` renders `<app-login>`
(`login/`) until `AuthCredentialsService.unlocked()` is true; only then do the
tabs and their content exist. The "password" on that screen *is* the shared
`API_BEARER_TOKEN`, and the "identifiant" is the `X-Actor-Id` — `Login`
validates them against `GET /api/v1/auth/session`
(`interface/api/routers/auth.py`, which just exposes `get_current_actor_id`
and adds no auth logic of its own), so credentials are verified server-side,
never compared in the browser. Session state lives in the shared
`AuthCredentialsService` (`services/auth-credentials.service.ts`), backed by
**`sessionStorage`** (not `localStorage`) so the gate closes when the browser
does; `unlocked` must stay a signal (it is written from a `.subscribe()` — see
the zoneless note below). `authInterceptor`
(`services/auth-interceptor.ts`, wired in `app.config.ts`) calls `lock()` on
any 401 so a rotated token can't leave the user "logged in" against failing
screens. Both tabs read `actorId`/`bearerToken` off the service when building
requests — don't reintroduce per-component credential fields; those inline
"Identification" fieldsets were removed when the gate landed. Note this gate
protects the *interface*, not the API: the API was already protected by the
same token, and a single shared token is still not an IAM (§13).

**This app has no `zone.js`** (not in `package.json`, nothing in
`app.config.ts`) — Angular 21's zoneless mode. Change detection only runs
after: a signal write, or a template-bound event handler
(`(click)`/`(change)`/`(ngModelChange)`/etc.) completing. A plain class field
mutated inside an RxJS `.subscribe()` callback (i.e. anything resolved async,
outside the synchronous call stack of a template event handler) will **not**
re-render the view — this bit `EventImport.events` during development (a
`FaceEvent[]` field set from an HTTP response never showed up in the
`<select>` until it was converted to a `signal<FaceEvent[]>`). Any state
written from a `.subscribe()`/`.then()` callback must be a signal; state only
ever mutated synchronously from a template event handler can stay a plain
field.

**Import progress is driven client-side, one image per request.** The admin
import route indexes synchronously and only answers once the whole batch is
done, so sending the batch in a single multipart request gives the UI no
intermediate signal at all. `EventImport` therefore owns the queue: it builds
one `ImportItem` per selected file (`models/import-progress.model.ts`) and
walks them sequentially through `EventImportService.uploadImage` (one image,
`observe: 'events'` + `reportProgress`), patching the item on each HTTP event.
Sequential, not parallel — the ONNX detector/embedder are single instances on
the API side. A failed image is recorded and the queue continues; cancelling
aborts the client request but the server still finishes the image already in
flight, hence status `cancelled` rather than a rollback. `ImportProgress`
(`import-progress/`) is presentational and derives everything from that list:
overall meter, counters, part-to-whole breakdowns (image outcomes, and
accepted-vs-rejected faces — the quality-gate rejection rate from §6.1), and
the per-image table. Status is never carried by color alone (icon + label
everywhere); `anyComponentStyle` budget in `angular.json` was raised from 4kB
to 8kB for that panel.

### Admin/import routes (`interface/api/routers/admin_events.py`)

`GET/POST /api/v1/admin/events` and `POST /api/v1/admin/events/{id}/images`
back the "Importer un événement" tab. Like `import_folder.py`, these are
dev/demo routes built on `infrastructure/devtools/event_import.py` (see the
port note above) — not part of the production API surface implied by the
technical scoping doc. Image indexing happens synchronously in the request
(calls `ProcessImageMessageUseCase` directly, reusing the detector/embedder/
object storage singletons from `app.state` via the existing `deps.py`
providers) rather than going through the Redis queue + worker — intentional,
so the UI gets an immediate per-image accepted/rejected count instead of
having to poll.

### Re-indexing from the dashboard

The **Tableau de bord** tab has a button that calls
`POST /api/v1/admin/indexing/trigger` (`routers/indexing.py`) for the images
still waiting. Two things the UI is careful about, and any change here must
preserve:

- **Queuing is not indexing.** The endpoint only publishes to the Redis stream;
  the *worker* does the work. The UI never says "indexed" after a successful
  trigger — it says "mise en file", then polls `GET /api/v1/stats` every 2s and
  lets the pending counter fall.
- **A worker that isn't running looks exactly like a slow one.** If nothing has
  been consumed after 15s, the UI stops polling and says the worker is probably
  down (`make worker`, or `make start`). Without that, the queue fills silently
  and the user waits forever. Re-triggering is safe — indexing is idempotent on
  `(image_id, model_version, face_index)`.

### Worker supervision (`GET /api/v1/admin/workers`)

Shown as a card on the **Tableau de bord**. Same read-port shape as the stats
endpoint: `QueueMonitorPort` (`domain/ports/queue_monitor.py`) →
`GetIndexingQueueStatusUseCase` → `RedisQueueMonitor`
(`infrastructure/messaging/redis_queue_monitor.py`, using `XINFO GROUPS` /
`XINFO CONSUMERS` / `XLEN`). It is deliberately kept apart from
`MessageQueuePort`, which the pipeline depends on to publish/read/ack — that
contract has no business carrying introspection methods.

**Redis registers consumers, not processes.** A consumer entry outlives the
worker that created it and carries no liveness flag; the only signal is
activity. So the vocabulary is `is_active` (polled recently — threshold
`ACTIVE_IDLE_THRESHOLD_SECONDS`, 30s) and never "running", and the UI says
"silencieux", explaining that this is either a dead process or a live one with
nothing to do. A killed worker keeps showing as active until the threshold
elapses; that lag is inherent, not a bug.

`is_stalled` (backlog > 0 with no active consumer) is the one actionable
diagnostic — it replaced the dashboard's earlier "pending hasn't moved in 15s"
heuristic, which is now only a fallback if this endpoint is unreachable.

**Each worker derives a unique consumer name** (`<host>-<pid>`,
`default_consumer_name()` in `interface/worker/indexing_worker.py`). The name
used to be hardcoded, so every process registered as the same consumer: they
were indistinguishable in supervision and, worse, reclaimed each other's
in-flight messages through `XAUTOCLAIM`, re-processing images already taken.

### Dashboard read model (`GET /api/v1/stats`)

Backs the **Tableau de bord** tab. It is a **read model, not observability** —
Lot 3 (metrics, traces, alerting) stays deliberately unimplemented, and this
endpoint takes a snapshot on demand with no history or time series. Don't grow
it into a metrics pipeline without revisiting that decision.

It goes through the full seam rather than querying the DB from the router:
`StatisticsPort` (`domain/ports/statistics.py`) → `GetSystemStatisticsUseCase`
→ `PostgresStatisticsRepository` (`infrastructure/db/statistics_pg.py`), wired
in `deps.py`. This is a *read* port, kept separate from the write repositories
so counting methods don't pollute their contracts. It is **not** the devtools
escape hatch used by `admin_events`/`import_folder`: a dashboard is a product
feature, not tooling, so the boundary holds.

Raw counters come from SQL; the **rates are computed in the domain**
(`domain/value_objects/system_statistics.py`) because their denominators encode
real decisions, unit-tested in `tests/unit/domain/test_system_statistics.py`:

- `quality_rejection_rate` is over *detected faces* (kept + rejected), not images.
- `average_faces_per_indexed_image` divides by **indexed** images — counting
  pending ones, which produced no faces yet, would flatten the average.
- `average_top_score` averages only *successful* searches (`top_score IS NOT NULL`).
- Every rate returns `0.0` when its denominator is zero — "nothing to measure",
  not an error. A fresh install must render, not crash.
- `__post_init__` rejects negative counters and subset-larger-than-set
  (`indexed > total`), which would mean the aggregate query is wrong.

Two indicators exist to answer open questions the README raises rather than as
filler: `quality_rejection_rate` + `rejections_by_reason` make the quality gate
(§6.1) tunable, and `empty_search_rate` + `average_top_score` are the first
signals on the uncalibrated 0.38 similarity threshold (§10.2).

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
