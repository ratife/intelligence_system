import pytest
from sqlalchemy import text

from facereco.domain.entities.event import IndexStatus
from facereco.domain.value_objects.model_version import ModelVersion
from facereco.infrastructure.db.event_repository_pg import PostgresEventRepository

pytestmark = pytest.mark.integration


def _insert_event(session, event_id: int) -> None:
    session.execute(
        text(
            "INSERT INTO events (id, title, description, event_date, address) "
            "VALUES (:id, 'Séminaire', 'Restitution annuelle.', '2026-03-14', 'Antananarivo')"
        ),
        {"id": event_id},
    )


def _insert_image(session, image_id: int, event_id: int, status: str) -> None:
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


def test_get_event_returns_none_when_missing(db_session) -> None:
    repository = PostgresEventRepository(db_session)
    assert repository.get_event(999) is None


def test_get_event_returns_entity(db_session) -> None:
    _insert_event(db_session, 1)
    db_session.commit()

    repository = PostgresEventRepository(db_session)
    event = repository.get_event(1)

    assert event is not None
    # Les deux, et avec des valeurs distinctes : c'est le seul test qui couvre
    # le chemin ORM `EventModel` → `_to_event`, celui qu'emprunte la recherche.
    assert event.title == "Séminaire"
    assert event.description == "Restitution annuelle."
    assert event.address == "Antananarivo"


def test_list_images_needing_indexing_returns_pending_and_failed(db_session) -> None:
    _insert_event(db_session, 1)
    _insert_image(db_session, 1, 1, "pending")
    _insert_image(db_session, 2, 1, "done")
    _insert_image(db_session, 3, 1, "failed")
    # image 2 est "done" ET déjà indexée pour cette version : elle ne doit pas
    # remonter, contrairement au cas testé séparément (nouvelle version de modèle).
    db_session.execute(
        text(
            "INSERT INTO face_embeddings (image_id, event_id, face_index, bbox, det_score, "
            "quality_score, embedding, model_version) VALUES "
            "(2, 1, 0, '{0,0,10,10}', 0.9, 0.9, :embedding, 'arcface-r100-v1')"
        ),
        {"embedding": str([0.1] * 512)},
    )
    db_session.commit()

    repository = PostgresEventRepository(db_session)
    images = repository.list_images_needing_indexing(
        model_version=ModelVersion(value="arcface-r100-v1"), limit=10
    )

    assert {img.id for img in images} == {1, 3}


def test_list_images_needing_indexing_includes_done_images_without_embedding_for_new_version(
    db_session,
) -> None:
    _insert_event(db_session, 1)
    _insert_image(db_session, 1, 1, "done")
    db_session.execute(
        text(
            "INSERT INTO face_embeddings (image_id, event_id, face_index, bbox, det_score, "
            "quality_score, embedding, model_version) VALUES "
            "(1, 1, 0, '{0,0,10,10}', 0.9, 0.9, :embedding, 'arcface-r100-v1')"
        ),
        {"embedding": str([0.1] * 512)},
    )
    db_session.commit()

    repository = PostgresEventRepository(db_session)
    images_old_version = repository.list_images_needing_indexing(
        model_version=ModelVersion(value="arcface-r100-v1"), limit=10
    )
    images_new_version = repository.list_images_needing_indexing(
        model_version=ModelVersion(value="arcface-r100-v2"), limit=10
    )

    assert images_old_version == []
    assert {img.id for img in images_new_version} == {1}


def test_mark_image_index_status_updates_row(db_session) -> None:
    _insert_event(db_session, 1)
    _insert_image(db_session, 1, 1, "pending")
    db_session.commit()

    repository = PostgresEventRepository(db_session)
    repository.mark_image_index_status(image_id=1, status=IndexStatus.DONE, indexed_at=None)
    db_session.commit()

    image = repository.get_image(1)
    assert image is not None
    assert image.index_status == IndexStatus.DONE
