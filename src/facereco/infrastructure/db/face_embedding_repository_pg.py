"""Implémentation PostgreSQL du port FaceEmbeddingRepositoryPort.

L'upsert idempotent (ON CONFLICT DO NOTHING sur la clé image_id/model_version/
face_index) garantit qu'un rejeu de message n'introduit jamais de doublon de
vecteur (P4).
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.orm import Session

from facereco.domain.entities.face import FaceEmbedding
from facereco.domain.ports.face_embedding_repository import FaceEmbeddingRepositoryPort
from facereco.infrastructure.db.models import FaceEmbeddingModel, RejectedFaceModel


class PostgresFaceEmbeddingRepository(FaceEmbeddingRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def save_embeddings(self, embeddings: list[FaceEmbedding]) -> None:
        if not embeddings:
            return
        now = datetime.now(UTC)
        rows = [
            {
                "image_id": e.image_id,
                "event_id": e.event_id,
                "face_index": e.face_index,
                "bbox": list(e.bbox.as_tuple()),
                "det_score": e.detection_score,
                "quality_score": e.quality_score,
                "embedding": list(e.embedding.values),
                "model_version": str(e.model_version),
                "created_at": now,
            }
            for e in embeddings
        ]
        stmt = pg_insert(FaceEmbeddingModel).values(rows)
        stmt = stmt.on_conflict_do_nothing(
            index_elements=["image_id", "model_version", "face_index"]
        )
        self._session.execute(stmt)

    def record_rejected_face(self, image_id: int, face_index: int, rejection_reason: str) -> None:
        self._session.add(
            RejectedFaceModel(
                image_id=image_id,
                face_index=face_index,
                rejection_reason=rejection_reason,
                created_at=datetime.now(UTC),
            )
        )
