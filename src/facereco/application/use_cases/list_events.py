"""Use case de parcours du catalogue d'événements.

Lecture seule : aucune écriture, aucun quota, aucune entrée d'audit — consulter
la liste de ce qui est indexé n'est pas une recherche de personne (ADR 008 vise
les recherches par visage, qui interrogent les empreintes).
"""

from __future__ import annotations

from facereco.application.dto import ListEventsCommand
from facereco.domain.ports.event_catalog import EventCatalogPort
from facereco.domain.value_objects.event_catalog import EventCatalogPage
from facereco.domain.value_objects.model_version import ModelVersion


class ListEventsUseCase:
    def __init__(self, catalog: EventCatalogPort, current_model_version: ModelVersion) -> None:
        self._catalog = catalog
        self._model_version = current_model_version

    def execute(self, command: ListEventsCommand) -> EventCatalogPage:
        """La tranche demandée, comptée pour la version de modèle courante.

        La pagination est bornée côté appelant (`ListEventsCommand` refuse une
        limite nulle ou négative) : une liste d'événements sans borne est une
        requête qui grossit en silence avec la base.
        """
        return self._catalog.list_events(
            model_version=self._model_version,
            limit=command.limit,
            offset=command.offset,
        )
