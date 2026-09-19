import pytest
from sqlalchemy import text

from facereco.domain.entities.face import FaceEmbedding
from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.domain.value_objects.embedding_vector import EMBEDDING_DIMENSION, EmbeddingVector
from facereco.domain.value_objects.model_version import ModelVersion
from facereco.infrastructure.db.face_embedding_repository_pg import (
    PostgresFaceEmbeddingRepository,
)

pytestmark = pytest.mark.integration


def _unit_embedding(index: int) -> EmbeddingVector:
    values = [0.0] * EMBEDDING_DIMENSION
    values[index] = 1.0
    return EmbeddingVector(values=tuple(values))


def _seed_event_and_image(session) -> None:
    session.execute(
        text(
            "INSERT INTO events (id, title, description, event_date, address) "
            "VALUES (1, 'Séminaire', '', '2026-03-14', 'Antananarivo')"
        )
    )
    session.execute(
        text(
            "INSERT INTO event_images (id, event_id, storage_uri, content_hash) "
            "VALUES (1, 1, 's3://bucket/1.jpg', 'hash-1')"
        )
    )
    session.commit()


def _embedding(face_index: int) -> FaceEmbedding:
    return FaceEmbedding(
        id=None,
        image_id=1,
        event_id=1,
        face_index=face_index,
        bbox=BoundingBox(x=0, y=0, width=80, height=80),
        detection_score=0.9,
        quality_score=0.9,
        embedding=_unit_embedding(face_index),
        model_version=ModelVersion(value="arcface-r100-v1"),
    )


def test_save_embeddings_persists_rows(db_session) -> None:
    _seed_event_and_image(db_session)
    repository = PostgresFaceEmbeddingRepository(db_session)

    repository.save_embeddings([_embedding(0), _embedding(1)])
    db_session.commit()

    count = db_session.execute(text("SELECT COUNT(*) FROM face_embeddings")).scalar_one()
    assert count == 2


def test_save_embeddings_is_idempotent_on_replay(db_session) -> None:
    _seed_event_and_image(db_session)
    repository = PostgresFaceEmbeddingRepository(db_session)

    repository.save_embeddings([_embedding(0)])
    db_session.commit()
    repository.save_embeddings([_embedding(0)])  # rejeu du même message
    db_session.commit()

    count = db_session.execute(text("SELECT COUNT(*) FROM face_embeddings")).scalar_one()
    assert count == 1


def test_record_rejected_face_persists_reason(db_session) -> None:
    _seed_event_and_image(db_session)
    repository = PostgresFaceEmbeddingRepository(db_session)

    repository.record_rejected_face(image_id=1, face_index=0, rejection_reason="taille_visage<40px")
    db_session.commit()

    row = db_session.execute(text("SELECT rejection_reason FROM rejected_faces")).one()
    assert row.rejection_reason == "taille_visage<40px"
