"""Use case du composant « Scanner / CDC » : détecte les images à (ré)indexer et les publie.

Le mode backfill (historique complet) et le mode incrémental (nouvelles images)
utilisent le même producteur — seule la requête de sélection diffère côté
Infrastructure (§6.1 « idempotence et versionnement »).
"""

from __future__ import annotations

from dataclasses import dataclass

from facereco.application.dto import TriggerIndexingCommand
from facereco.domain.ports.event_repository import EventRepositoryPort
from facereco.domain.ports.message_queue import MessageQueuePort
from facereco.domain.value_objects.model_version import ModelVersion


@dataclass(frozen=True, slots=True)
class TriggerIndexingResult:
    images_published: int


class TriggerIndexingUseCase:
    def __init__(
        self,
        event_repository: EventRepositoryPort,
        message_queue: MessageQueuePort,
        current_model_version: ModelVersion,
    ) -> None:
        self._event_repository = event_repository
        self._message_queue = message_queue
        self._current_model_version = current_model_version

    def execute(self, command: TriggerIndexingCommand) -> TriggerIndexingResult:
        pending_images = self._event_repository.list_images_needing_indexing(
            model_version=self._current_model_version,
            limit=command.batch_limit,
        )
        for image in pending_images:
            self._message_queue.publish_image_for_indexing(image.id)
        return TriggerIndexingResult(images_published=len(pending_images))
