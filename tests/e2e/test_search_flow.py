"""Test e2e : indexation d'une image puis recherche par visage via l'API HTTP.

Les adapters ML sont des fakes déterministes (voir conftest) — ce test valide
le câblage Interface → Application → Domain → Infrastructure(Postgres réel),
pas la précision d'un modèle ML réel (couverte séparément en tests/integration/ml).
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from facereco.application.dto import IndexImageCommand
from facereco.application.use_cases.process_image_message import ProcessImageMessageUseCase
from facereco.infrastructure.db.event_repository_pg import PostgresEventRepository
from facereco.infrastructure.db.face_embedding_repository_pg import (
    PostgresFaceEmbeddingRepository,
)
from facereco.infrastructure.system_clock import SystemClock
from tests.e2e.conftest import ACTOR_HEADERS

pytestmark = pytest.mark.e2e

PHOTO_BYTES = b"query-image-bytes"  # doit correspondre à `query_image` du conftest e2e


def _seed_and_index(test_app, session) -> None:
    session.execute(
        text(
            "INSERT INTO events (id, description, event_date, address) VALUES "
            "(1, 'Séminaire annuel', '2026-03-14', 'Antananarivo')"
        )
    )
    session.execute(
        text(
            "INSERT INTO event_images (id, event_id, storage_uri, content_hash) VALUES "
            "(1, 1, 's3://bucket/photo.jpg', 'hash-photo')"
        )
    )
    session.commit()

    test_app.state.object_storage.images["s3://bucket/photo.jpg"] = PHOTO_BYTES

    use_case = ProcessImageMessageUseCase(
        event_repository=PostgresEventRepository(session),
        object_storage=test_app.state.object_storage,
        face_detector=test_app.state.face_detector,
        face_embedder=test_app.state.face_embedder,
        face_embedding_repository=PostgresFaceEmbeddingRepository(session),
        clock=SystemClock(),
    )
    result = use_case.execute(IndexImageCommand(image_id=1))
    session.commit()
    assert result.faces_accepted == 1


def test_search_by_face_finds_indexed_event(client, test_app) -> None:
    from facereco.infrastructure.db.session import SessionFactory

    session = SessionFactory()
    try:
        _seed_and_index(test_app, session)
    finally:
        session.close()

    response = client.post(
        "/api/v1/search/by-face",
        headers=ACTOR_HEADERS,
        files={"image": ("photo.jpg", PHOTO_BYTES, "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["query"]["faces_detected"] == 1
    assert len(body["results"]) == 1
    assert body["results"][0]["event_id"] == 1
    assert body["results"][0]["description"] == "Séminaire annuel"
    assert body["results"][0]["confidence"] == pytest.approx(1.0 + 0.02 * 0.6931, abs=1e-3)


def test_search_by_face_returns_409_when_no_face_detected(client) -> None:
    response = client.post(
        "/api/v1/search/by-face",
        headers=ACTOR_HEADERS,
        files={"image": ("empty.jpg", b"unknown-bytes-without-face", "image/jpeg")},
    )

    assert response.status_code == 409


def test_search_by_face_requires_authentication(client) -> None:
    response = client.post(
        "/api/v1/search/by-face",
        files={"image": ("photo.jpg", PHOTO_BYTES, "image/jpeg")},
    )

    assert response.status_code in (401, 422)
