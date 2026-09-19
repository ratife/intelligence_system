"""Tests e2e du catalogue d'événements — GET /api/v1/events[/{id}].

Postgres est réel (le SQL d'agrégation fait partie du contrat) ; le stockage
objet est remplacé par un fake, dont les URLs signées suffisent à vérifier que
la route n'expose jamais l'URI de stockage brute.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.e2e.conftest import ACTOR_HEADERS

pytestmark = pytest.mark.e2e

ZERO_VECTOR = "[" + ",".join(["0"] * 511) + ",1]"
MODEL_VERSION = "arcface-r100-v1"  # doit correspondre au fake embedder du conftest


def _seed(session) -> None:
    session.execute(
        text(
            "INSERT INTO events (id, title, description, event_date, address) VALUES "
            "(1, 'Séminaire annuel', 'Trois jours de restitution.', '2026-03-14', 'Antananarivo'), "
            "(2, 'Remise de diplômes', '', '2026-06-30', 'Fianarantsoa')"
        )
    )
    session.execute(
        text(
            "INSERT INTO event_images (id, event_id, storage_uri, content_hash, index_status) "
            "VALUES (1, 1, 's3://bucket/photo.jpg', 'hash-photo', 'done'), "
            "(2, 1, 's3://bucket/attente.jpg', 'hash-attente', 'pending')"
        )
    )
    session.execute(
        text(
            "INSERT INTO face_embeddings (image_id, event_id, face_index, bbox, det_score, "
            "quality_score, embedding, model_version, created_at) VALUES "
            "(1, 1, 0, '{12,34,56,78}', 0.93, 0.81, :embedding, :model, now())"
        ),
        {"embedding": ZERO_VECTOR, "model": MODEL_VERSION},
    )
    session.execute(
        text(
            "INSERT INTO rejected_faces (image_id, face_index, rejection_reason, created_at) "
            "VALUES (1, 1, 'flou<80', now())"
        )
    )
    session.commit()


@pytest.fixture()
def seeded(test_app):
    from facereco.infrastructure.db.session import SessionFactory

    session = SessionFactory()
    try:
        _seed(session)
    finally:
        session.close()


def test_lists_events_most_recent_first_with_their_indexing_state(client, seeded) -> None:
    response = client.get("/api/v1/events", headers=ACTOR_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["total_count"] == 2
    assert body["offset"] == 0
    assert body["has_more"] is False
    assert [event["id"] for event in body["events"]] == [2, 1]

    seminaire = body["events"][1]
    assert seminaire["image_count"] == 2
    assert seminaire["indexed_image_count"] == 1
    assert seminaire["pending_image_count"] == 1
    assert seminaire["face_count"] == 1
    assert seminaire["discarded_face_count"] == 1
    assert seminaire["indexing_completion_rate"] == pytest.approx(0.5)
    assert seminaire["quality_rejection_rate"] == pytest.approx(0.5)
    assert seminaire["is_searchable"] is True


def test_event_without_retained_face_is_flagged_unsearchable(client, seeded) -> None:
    """Le diagnostic utile : « Remise de diplômes » n'a aucune image, donc aucun
    visage — aucune recherche ne peut la faire ressortir."""
    body = client.get("/api/v1/events", headers=ACTOR_HEADERS).json()
    diplomes = next(event for event in body["events"] if event["id"] == 2)

    assert diplomes["face_count"] == 0
    assert diplomes["is_searchable"] is False


def test_pagination_reports_its_position(client, seeded) -> None:
    body = client.get("/api/v1/events?limit=1&offset=0", headers=ACTOR_HEADERS).json()
    assert [event["id"] for event in body["events"]] == [2]
    assert body["has_more"] is True

    last = client.get("/api/v1/events?limit=1&offset=1", headers=ACTOR_HEADERS).json()
    assert [event["id"] for event in last["events"]] == [1]
    assert last["offset"] == 1
    assert last["has_more"] is False


def test_detail_returns_faces_with_signed_urls_never_storage_uris(client, seeded) -> None:
    response = client.get("/api/v1/events/1", headers=ACTOR_HEADERS)

    assert response.status_code == 200
    body = response.json()
    assert body["event"]["title"] == "Séminaire annuel"
    assert body["event"]["description"] == "Trois jours de restitution."
    assert [image["image_id"] for image in body["images"]] == [1, 2]

    indexed, pending = body["images"]
    assert indexed["index_status"] == "done"
    assert indexed["indexed_faces"] == [
        {"face_index": 0, "bbox": [12, 34, 56, 78], "detection_score": 0.93, "quality_score": 0.81}
    ]
    assert indexed["discarded_faces"] == [{"face_index": 1, "reason": "flou<80"}]
    assert pending["index_status"] == "pending"
    assert pending["indexed_faces"] == []

    # §12 : jamais d'accès direct au stockage.
    assert not indexed["image_url"].startswith("s3://")
    assert "s3://bucket/photo.jpg" in indexed["image_url"]


def test_detail_of_unknown_event_is_404(client) -> None:
    """`EventNotFoundError` est déjà traduite par `error_handlers.py`."""
    assert client.get("/api/v1/events/999", headers=ACTOR_HEADERS).status_code == 404


def test_page_size_is_bounded(client, seeded) -> None:
    """Une limite non bornée est une requête qui grossit avec la base."""
    assert client.get("/api/v1/events?limit=0", headers=ACTOR_HEADERS).status_code == 422
    assert client.get("/api/v1/events?limit=9999", headers=ACTOR_HEADERS).status_code == 422


def test_requires_authentication(client) -> None:
    assert client.get("/api/v1/events").status_code == 422
