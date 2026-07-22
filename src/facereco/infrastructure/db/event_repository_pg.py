"""Implémentation PostgreSQL du port EventRepositoryPort."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import exists, or_, select
from sqlalchemy.orm import Session

from facereco.domain.entities.event import Event, EventImage, IndexStatus
from facereco.domain.ports.event_repository import EventRepositoryPort
from facereco.domain.value_objects.model_version import ModelVersion
from facereco.infrastructure.db.models import EventImageModel, EventModel, FaceEmbeddingModel


def _to_event(row: EventModel) -> Event:
    return Event(
        id=row.id, description=row.description, event_date=row.event_date, address=row.address
    )


def _to_event_image(row: EventImageModel) -> EventImage:
    return EventImage(
        id=row.id,
        event_id=row.event_id,
        storage_uri=row.storage_uri,
        content_hash=row.content_hash,
        width=row.width or 0,
        height=row.height or 0,
        index_status=IndexStatus(row.index_status),
        indexed_at=row.indexed_at,
    )


class PostgresEventRepository(EventRepositoryPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def get_event(self, event_id: int) -> Event | None:
        row = self._session.get(EventModel, event_id)
        return _to_event(row) if row else None

    def get_events_by_ids(self, event_ids: list[int]) -> dict[int, Event]:
        if not event_ids:
            return {}
        rows = self._session.scalars(select(EventModel).where(EventModel.id.in_(event_ids))).all()
        return {row.id: _to_event(row) for row in rows}

    def get_image(self, image_id: int) -> EventImage | None:
        row = self._session.get(EventImageModel, image_id)
        return _to_event_image(row) if row else None

    def list_images_needing_indexing(
        self, model_version: ModelVersion, limit: int
    ) -> list[EventImage]:
        already_indexed_for_version = select(FaceEmbeddingModel.image_id).where(
            FaceEmbeddingModel.image_id == EventImageModel.id,
            FaceEmbeddingModel.model_version == str(model_version),
        )
        query = (
            select(EventImageModel)
            .where(
                or_(
                    EventImageModel.index_status.in_(
                        [IndexStatus.PENDING.value, IndexStatus.FAILED.value]
                    ),
                    ~exists(already_indexed_for_version),
                )
            )
            .order_by(EventImageModel.id)
            .limit(limit)
        )
        rows = self._session.scalars(query).all()
        return [_to_event_image(row) for row in rows]

    def mark_image_index_status(
        self, image_id: int, status: IndexStatus, indexed_at: datetime | None
    ) -> None:
        row = self._session.get(EventImageModel, image_id)
        if row is None:
            return
        row.index_status = status.value
        row.indexed_at = indexed_at
        self._session.add(row)
