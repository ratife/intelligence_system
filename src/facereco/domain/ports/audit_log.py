"""Port du journal d'audit des recherches — exigence de conformité non désactivable (ADR 008).

Principale défense en cas de contrôle ou de contestation : toute recherche est
tracée (qui, quand, empreinte de l'image requête — jamais l'image elle-même,
résultats retournés).
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from facereco.domain.value_objects.model_version import ModelVersion


class AuditLogPort(ABC):
    @abstractmethod
    def record_search(
        self,
        actor_id: str,
        query_hash: str,
        result_count: int,
        top_score: float | None,
        threshold_used: float,
        model_version: ModelVersion,
    ) -> None:
        raise NotImplementedError
