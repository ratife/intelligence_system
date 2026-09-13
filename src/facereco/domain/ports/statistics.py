"""Port du modèle de lecture des statistiques système (tableau de bord).

Port de *lecture* : il ne sert aucune règle métier et n'est appelé par aucun
pipeline (indexation, recherche). Il expose une projection agrégée de l'état de
la base, séparée des repositories d'écriture — dont les méthodes de comptage
n'ont pas à polluer les contrats.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from facereco.domain.value_objects.system_statistics import SystemStatistics


class StatisticsPort(ABC):
    @abstractmethod
    def collect(self) -> SystemStatistics:
        """Agrège l'état courant du système en une photographie chiffrée."""
        raise NotImplementedError
