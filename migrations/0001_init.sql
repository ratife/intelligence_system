-- Schéma initial — reprend le §8 du cadrage technique, étendu avec rejected_faces
-- (traçabilité des rejets qualité, §6.1) et la table events de développement
-- (rappel : en production, events est un schéma déjà existant chez le client).

CREATE EXTENSION IF NOT EXISTS vector;

CREATE TABLE IF NOT EXISTS events (
    id              BIGSERIAL PRIMARY KEY,
    description     TEXT NOT NULL,
    event_date      DATE NOT NULL,
    address         TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS event_images (
    id              BIGSERIAL PRIMARY KEY,
    event_id        BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    storage_uri     TEXT NOT NULL,
    content_hash    CHAR(64) NOT NULL,
    width           INT,
    height          INT,
    indexed_at      TIMESTAMPTZ,
    index_status    TEXT NOT NULL DEFAULT 'pending',
    UNIQUE (content_hash)
);

CREATE TABLE IF NOT EXISTS person_clusters (
    id              BIGSERIAL PRIMARY KEY,
    centroid        vector(512) NOT NULL,
    face_count      INT NOT NULL DEFAULT 0,
    consent_state   TEXT NOT NULL DEFAULT 'unknown',
    purge_after     TIMESTAMPTZ
);

CREATE TABLE IF NOT EXISTS face_embeddings (
    id              BIGSERIAL PRIMARY KEY,
    image_id        BIGINT NOT NULL REFERENCES event_images(id) ON DELETE CASCADE,
    event_id        BIGINT NOT NULL REFERENCES events(id) ON DELETE CASCADE,
    face_index      SMALLINT NOT NULL,
    bbox            INT[4] NOT NULL,
    det_score       REAL NOT NULL,
    quality_score   REAL NOT NULL,
    embedding       vector(512) NOT NULL,
    model_version   TEXT NOT NULL,
    cluster_id      BIGINT REFERENCES person_clusters(id),
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (image_id, model_version, face_index)
);

CREATE INDEX IF NOT EXISTS idx_face_hnsw ON face_embeddings
    USING hnsw (embedding vector_cosine_ops)
    WITH (m = 16, ef_construction = 64);

CREATE INDEX IF NOT EXISTS idx_face_event ON face_embeddings (event_id);
CREATE INDEX IF NOT EXISTS idx_face_model_version ON face_embeddings (model_version);

-- Extension au schéma du document : traçabilité des rejets qualité (§6.1).
CREATE TABLE IF NOT EXISTS rejected_faces (
    id                  BIGSERIAL PRIMARY KEY,
    image_id            BIGINT NOT NULL REFERENCES event_images(id) ON DELETE CASCADE,
    face_index          SMALLINT NOT NULL,
    rejection_reason    TEXT NOT NULL,
    created_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Journal d'audit : exigence de conformité, non optionnel (ADR 008).
CREATE TABLE IF NOT EXISTS search_audit_log (
    id              BIGSERIAL PRIMARY KEY,
    actor_id        TEXT NOT NULL,
    query_hash      CHAR(64) NOT NULL,
    result_count    INT NOT NULL,
    top_score       REAL,
    threshold_used  REAL NOT NULL,
    model_version   TEXT NOT NULL,
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now()
);
