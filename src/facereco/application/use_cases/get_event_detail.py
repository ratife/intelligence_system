"""Use case de consultation du détail d'un événement.

Montre, image par image, ce que l'indexation a retenu et ce qu'elle a écarté.
Un événement inexistant lève `EventNotFoundError` plutôt que de renvoyer un
détail vide : l'Interface la traduit déjà en 404 (`error_handlers.py`), et un
détail vide se confondrait avec un événement réellement sans image.
"""

from __future__ import annotations

from facereco.application.dto import GetEventDetailCommand
from facereco.domain.exceptions import EventNotFoundError
from facereco.domain.ports.event_catalog import EventCatalogPort
from facereco.domain.value_objects.event_catalog import EventDetail
from facereco.domain.value_objects.model_version import ModelVersion


class GetEventDetailUseCase:
    def __init__(self, catalog: EventCatalogPort, current_model_version: ModelVersion) -> None:
        self._catalog = catalog
        self._model_version = current_model_version

    def execute(self, command: GetEventDetailCommand) -> EventDetail:
        detail = self._catalog.get_event_detail(command.event_id, self._model_version)
        if detail is None:
            raise EventNotFoundError(command.event_id)
        return detail
