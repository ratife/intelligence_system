"""Implémentation pgvector du port VectorSearchPort (index HNSW, distance cosinus).

Requête directement inspirée de celle du §8 du cadrage technique, étendue avec
un filtre optionnel par date d'événement, appliqué *avant* la recherche
vectorielle (§7.3 — gain de performance via les index partiels de pgvector).
"""

from __future__ import annotations

from datetime import date

from sqlalchemy import text
from sqlalchemy.orm import Session

from facereco.domain.ports.vector_search import VectorSearchHit, VectorSearchPort
from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.domain.value_objects.embedding_vector import EmbeddingVector
from facereco.domain.value_objects.model_version import ModelVersion

_SEARCH_SQL = text(
    """
    SELECT fe.event_id, fe.image_id, ei.storage_uri, fe.bbox,
           1 - (fe.embedding <=> (:query_vector)::vector) AS similarity
    FROM face_embeddings fe
    JOIN event_images ei ON ei.id = fe.image_id
    JOIN events e ON e.id = fe.event_id
    WHERE fe.model_version = :model_version
      AND fe.quality_score >= :min_quality_score
      AND ((:date_from)::date IS NULL OR e.event_date >= (:date_from)::date)
      AND ((:date_to)::date IS NULL OR e.event_date <= (:date_to)::date)
    ORDER BY fe.embedding <=> (:query_vector)::vector
    LIMIT :top_k
    """
)


def _format_vector(values: tuple[float, ...]) -> str:
    return "[" + ",".join(repr(v) for v in values) + "]"


class PgVectorSearch(VectorSearchPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def search_top_k(
        self,
        query: EmbeddingVector,
        model_version: ModelVersion,
        top_k: int,
        min_quality_score: float,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[VectorSearchHit]:
        rows = self._session.execute(
            _SEARCH_SQL,
            {
                "query_vector": _format_vector(query.values),
                "model_version": str(model_version),
                "min_quality_score": min_quality_score,
                "date_from": date_from,
                "date_to": date_to,
                "top_k": top_k,
            },
        ).all()
        return [
            VectorSearchHit(
                event_id=row.event_id,
                image_id=row.image_id,
                storage_uri=row.storage_uri,
                bbox=BoundingBox(
                    x=row.bbox[0], y=row.bbox[1], width=row.bbox[2], height=row.bbox[3]
                ),
                similarity=float(row.similarity),
            )
            for row in rows
        ]
