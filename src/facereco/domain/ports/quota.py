"""Port de quota de recherche par acteur — mesure de conformité, pas seulement de performance.

Un accès sans limite de débit transforme le service de recherche en outil de
profilage de masse (§12, « principes de conception de l'API »).
"""

from __future__ import annotations

from abc import ABC, abstractmethod


class SearchQuotaPort(ABC):
    @abstractmethod
    def check_and_consume(self, actor_id: str) -> bool:
        """Consomme une unité de quota pour l'acteur ; retourne False si le quota est épuisé."""
        raise NotImplementedError
