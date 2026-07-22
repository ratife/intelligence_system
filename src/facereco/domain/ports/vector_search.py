"""Port de recherche par similarité vectorielle (ANN) — implémenté via pgvector/HNSW.

Interface applicative unique (P6/ADR002) : c'est le seul point de contact entre
le domaine et le moteur vectoriel, ce qui permet de faire migrer l'implémentation
(pgvector → Qdrant) sans jamais modifier le domaine ni les use cases.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass
from datetime import date

from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.domain.value_objects.embedding_vector import EmbeddingVector
from facereco.domain.value_objects.model_version import ModelVersion


@dataclass(frozen=True, slots=True)
class VectorSearchHit:
    """Un visage candidat brut retourné par l'index ANN, avant regroupement par événement."""

    event_id: int
    image_id: int
    storage_uri: str
    bbox: BoundingBox
    similarity: float


class VectorSearchPort(ABC):
    @abstractmethod
    def search_top_k(
        self,
        query: EmbeddingVector,
        model_version: ModelVersion,
        top_k: int,
        min_quality_score: float,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[VectorSearchHit]:
        """Top-K plus proches voisins (cosinus) — le filtrage par date, s'il est fourni,

        est appliqué avant la recherche vectorielle (§7.3 — gain de performance
        sur les gros volumes via les index partiels pgvector).
        """
        raise NotImplementedError
