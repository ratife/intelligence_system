"""Port de persistance pour les événements et leurs images."""

from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import datetime

from facereco.domain.entities.event import Event, EventImage, IndexStatus
from facereco.domain.value_objects.model_version import ModelVersion


class EventRepositoryPort(ABC):
    @abstractmethod
    def get_event(self, event_id: int) -> Event | None:
        raise NotImplementedError

    @abstractmethod
    def get_events_by_ids(self, event_ids: list[int]) -> dict[int, Event]:
        raise NotImplementedError

    @abstractmethod
    def get_image(self, image_id: int) -> EventImage | None:
        raise NotImplementedError

    @abstractmethod
    def list_images_needing_indexing(
        self, model_version: ModelVersion, limit: int
    ) -> list[EventImage]:
        """Images à (ré)indexer pour cette version de modèle (backfill + incrémental confondus)."""
        raise NotImplementedError

    @abstractmethod
    def mark_image_index_status(
        self, image_id: int, status: IndexStatus, indexed_at: datetime | None
    ) -> None:
        raise NotImplementedError
