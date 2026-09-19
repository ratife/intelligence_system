"""Tests d'intégration du catalogue : c'est le SQL d'agrégation qui est en jeu.

Les compteurs sont l'essentiel de cette fonctionnalité, et les pièges sont tous
dans la requête : produit cartésien entre images, visages et rejets, rejets
dupliqués en base, et visages d'une autre version de modèle.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from facereco.domain.entities.event import IndexStatus
from facereco.domain.value_objects.model_version import ModelVersion
from facereco.infrastructure.db.event_catalog_pg import PostgresEventCatalog

pytestmark = pytest.mark.integration

MODEL = ModelVersion(value="arcface-r100-v1")
OTHER_MODEL = ModelVersion(value="arcface-r50-v0")
ZERO_VECTOR = "[" + ",".join(["0"] * 511) + ",1]"


def _insert_event(session, event_id: int, event_date: str = "2026-03-14") -> None:
    session.execute(
        text(
            "INSERT INTO events (id, title, description, event_date, address) "
            "VALUES (:id, :title, :description, :event_date, 'Antananarivo')"
        ),
        {
            "id": event_id,
            # Titre et description délibérément différents : c'est ce qui fait
            # tomber le test si un SELECT nommé confond les deux colonnes.
            "title": f"Événement {event_id}",
            "description": f"Compte rendu de l'événement {event_id}.",
            "event_date": event_date,
        },
    )


def _insert_image(session, image_id: int, event_id: int, status: str = "done") -> None:
    session.execute(
        text(
            "INSERT INTO event_images (id, event_id, storage_uri, content_hash, index_status) "
            "VALUES (:id, :event_id, :uri, :hash, :status)"
        ),
        {
            "id": image_id,
            "event_id": event_id,
            "uri": f"s3://bucket/{image_id}.jpg",
            "hash": f"hash-{image_id}",
            "status": status,
        },
    )


def _insert_face(
    session, image_id: int, event_id: int, face_index: int, model: ModelVersion = MODEL
) -> None:
    session.execute(
        text(
            "INSERT INTO face_embeddings (image_id, event_id, face_index, bbox, det_score, "
            "quality_score, embedding, model_version, created_at) VALUES "
            "(:image_id, :event_id, :face_index, :bbox, 0.9, 0.8, :embedding, :model, now())"
        ),
        {
            "image_id": image_id,
            "event_id": event_id,
            "face_index": face_index,
            "bbox": [10 * face_index, 20, 30, 40],
            "embedding": ZERO_VECTOR,
            "model": str(model),
        },
    )


def _insert_rejection(session, image_id: int, face_index: int, reason: str) -> None:
    session.execute(
        text(
            "INSERT INTO rejected_faces (image_id, face_index, rejection_reason, created_at) "
            "VALUES (:image_id, :face_index, :reason, now())"
        ),
        {"image_id": image_id, "face_index": face_index, "reason": reason},
    )


def test_counters_are_not_inflated_by_joining_faces_and_rejections(db_session) -> None:
    """Le piège n°1 de cette requête : 2 images × 3 visages × 2 rejets à plat
    donnerait 12 lignes, donc 12 images. Les compteurs doivent rester 2/3/2."""
    _insert_event(db_session, 1)
    _insert_image(db_session, 10, 1)
    _insert_image(db_session, 11, 1)
    for face_index in range(3):
        _insert_face(db_session, 10, 1, face_index)
    _insert_rejection(db_session, 11, 0, "flou<80")
    _insert_rejection(db_session, 11, 1, "taille_visage<40px")
    db_session.commit()

    summary = PostgresEventCatalog(db_session).list_events(MODEL, limit=10, offset=0).events[0]

    assert summary.image_count == 2
    assert summary.face_count == 3
    assert summary.discarded_face_count == 2
    assert summary.detected_face_count == 5


def test_duplicated_rejections_are_counted_once(db_session) -> None:
    """`rejected_faces` n'a pas de contrainte d'unicité et une image dont tous
    les visages sont écartés reste réindexable : les mêmes rejets y sont
    réinsérés à chaque relance. Sans dédoublonnage, un visage écarté une fois
    s'afficherait « écarté trois fois »."""
    _insert_event(db_session, 1)
    _insert_image(db_session, 10, 1)
    for _ in range(3):
        _insert_rejection(db_session, 10, 0, "flou<80")
    db_session.commit()

    catalog = PostgresEventCatalog(db_session)

    assert catalog.list_events(MODEL, limit=10, offset=0).events[0].discarded_face_count == 1
    detail = catalog.get_event_detail(1, MODEL)
    assert detail is not None
    assert len(detail.images[0].discarded_faces) == 1


def test_faces_of_another_model_version_are_excluded(db_session) -> None:
    """Sinon une migration de modèle doublerait les visages, donc les cadres."""
    _insert_event(db_session, 1)
    _insert_image(db_session, 10, 1)
    _insert_face(db_session, 10, 1, 0, model=MODEL)
    _insert_face(db_session, 10, 1, 0, model=OTHER_MODEL)
    db_session.commit()

    catalog = PostgresEventCatalog(db_session)

    assert catalog.list_events(MODEL, limit=10, offset=0).events[0].face_count == 1
    detail = catalog.get_event_detail(1, MODEL)
    assert detail is not None
    assert len(detail.images[0].indexed_faces) == 1


def test_event_without_image_is_listed_with_zeros(db_session) -> None:
    """Un événement créé mais pas encore alimenté doit apparaître, pas disparaître."""
    _insert_event(db_session, 1)
    db_session.commit()

    page = PostgresEventCatalog(db_session).list_events(MODEL, limit=10, offset=0)

    assert page.total_count == 1
    assert page.events[0].image_count == 0
    assert page.events[0].indexing_completion_rate == 0.0
    assert page.events[0].is_searchable is False


def test_events_are_listed_most_recent_first_and_paginated(db_session) -> None:
    for event_id, event_date in ((1, "2026-01-10"), (2, "2026-05-20"), (3, "2026-03-14")):
        _insert_event(db_session, event_id, event_date)
    db_session.commit()

    catalog = PostgresEventCatalog(db_session)
    first = catalog.list_events(MODEL, limit=2, offset=0)
    second = catalog.list_events(MODEL, limit=2, offset=2)

    assert [summary.event.id for summary in first.events] == [2, 3]
    assert first.total_count == 3
    assert first.has_more is True
    assert [summary.event.id for summary in second.events] == [1]
    assert second.has_more is False


def test_detail_groups_faces_and_rejections_per_image(db_session) -> None:
    _insert_event(db_session, 1)
    _insert_image(db_session, 10, 1, status="done")
    _insert_image(db_session, 11, 1, status="pending")
    _insert_face(db_session, 10, 1, 0)
    _insert_face(db_session, 10, 1, 1)
    _insert_rejection(db_session, 10, 2, "yaw>45")
    db_session.commit()

    detail = PostgresEventCatalog(db_session).get_event_detail(1, MODEL)

    assert detail is not None
    assert [item.image.id for item in detail.images] == [10, 11]
    first, second = detail.images
    assert [face.face_index for face in first.indexed_faces] == [0, 1]
    assert first.indexed_faces[1].bbox.as_tuple() == (10, 20, 30, 40)
    assert [face.reason for face in first.discarded_faces] == ["yaw>45"]
    assert first.detected_face_count == 3
    assert second.indexed_faces == ()
    assert second.image.index_status is IndexStatus.PENDING
    # Les compteurs du résumé sont dérivés des listes affichées : ils ne peuvent
    # pas contredire le détail rendu juste en dessous.
    assert detail.summary.image_count == 2
    assert detail.summary.indexed_image_count == 1
    assert detail.summary.pending_image_count == 1
    assert detail.summary.face_count == 2
    assert detail.summary.discarded_face_count == 1


def test_detail_of_unknown_event_is_none(db_session) -> None:
    assert PostgresEventCatalog(db_session).get_event_detail(999, MODEL) is None
