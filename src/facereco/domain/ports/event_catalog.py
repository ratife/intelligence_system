"""Port du modèle de lecture du catalogue d'événements.

Port de *lecture*, comme `StatisticsPort` : il ne sert aucune règle métier et
n'est appelé par aucun pipeline (indexation, recherche). Il est délibérément
tenu à l'écart de `EventRepositoryPort`, dont le contrat sert le pipeline
d'indexation — y greffer des projections d'affichage le ferait grossir sans
raison métier.

Ce n'est pas non plus l'échappatoire d'outillage de `devtools/event_import.py` :
consulter le catalogue est une fonctionnalité produit, pas un utilitaire de
peuplement, donc la couture des ports s'applique pleinement.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from facereco.domain.value_objects.event_catalog import EventCatalogPage, EventDetail
from facereco.domain.value_objects.model_version import ModelVersion


class EventCatalogPort(ABC):
    @abstractmethod
    def list_events(self, model_version: ModelVersion, limit: int, offset: int) -> EventCatalogPage:
        """Tranche d'événements avec leurs compteurs, les plus récents d'abord.

        `model_version` cadre le comptage des visages : « indexé » n'a de sens
        que pour une version de modèle donnée — c'est déjà ce que suppose
        `EventRepositoryPort.list_images_needing_indexing`.
        """
        raise NotImplementedError

    @abstractmethod
    def get_event_detail(self, event_id: int, model_version: ModelVersion) -> EventDetail | None:
        """Détail image par image, ou None si l'événement n'existe pas."""
        raise NotImplementedError
