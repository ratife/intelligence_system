from datetime import date

import pytest
from sqlalchemy import text

from facereco.domain.value_objects.embedding_vector import EMBEDDING_DIMENSION, EmbeddingVector
from facereco.domain.value_objects.model_version import ModelVersion
from facereco.infrastructure.db.vector_search_pgvector import PgVectorSearch

pytestmark = pytest.mark.integration

MODEL_VERSION = ModelVersion(value="arcface-r100-v1")


def _unit_vector(index: int) -> EmbeddingVector:
    values = [0.0] * EMBEDDING_DIMENSION
    values[index] = 1.0
    return EmbeddingVector(values=tuple(values))


def _seed(session) -> None:
    session.execute(
        text(
            "INSERT INTO events (id, title, description, event_date, address) VALUES "
            "(1, 'Séminaire', '', '2026-03-14', 'Antananarivo'), "
            "(2, 'Conférence', '', '2026-06-01', 'Fianarantsoa')"
        )
    )
    session.execute(
        text(
            "INSERT INTO event_images (id, event_id, storage_uri, content_hash) VALUES "
            "(1, 1, 's3://bucket/1.jpg', 'h1'), (2, 2, 's3://bucket/2.jpg', 'h2')"
        )
    )
    session.execute(
        text(
            "INSERT INTO face_embeddings (image_id, event_id, face_index, bbox, det_score, "
            "quality_score, embedding, model_version) VALUES "
            "(1, 1, 0, '{0,0,10,10}', 0.9, 0.9, :v1, 'arcface-r100-v1'), "
            "(2, 2, 0, '{0,0,10,10}', 0.9, 0.9, :v2, 'arcface-r100-v1')"
        ),
        {"v1": str(list(_unit_vector(0).values)), "v2": str(list(_unit_vector(1).values))},
    )
    session.commit()


def test_search_top_k_returns_closest_vector_first(db_session) -> None:
    _seed(db_session)
    search = PgVectorSearch(db_session)

    hits = search.search_top_k(
        query=_unit_vector(0),
        model_version=MODEL_VERSION,
        top_k=10,
        min_quality_score=0.5,
    )

    assert hits[0].event_id == 1
    assert hits[0].similarity == pytest.approx(1.0, abs=1e-4)
    assert hits[1].event_id == 2
    assert hits[1].similarity == pytest.approx(0.0, abs=1e-4)


def test_search_top_k_filters_by_date_range(db_session) -> None:
    _seed(db_session)
    search = PgVectorSearch(db_session)

    hits = search.search_top_k(
        query=_unit_vector(0),
        model_version=MODEL_VERSION,
        top_k=10,
        min_quality_score=0.5,
        date_from=date(2026, 5, 1),
    )

    assert [hit.event_id for hit in hits] == [2]


def test_search_top_k_filters_by_model_version(db_session) -> None:
    _seed(db_session)
    search = PgVectorSearch(db_session)

    hits = search.search_top_k(
        query=_unit_vector(0),
        model_version=ModelVersion(value="arcface-r100-v2"),
        top_k=10,
        min_quality_score=0.5,
    )

    assert hits == []
