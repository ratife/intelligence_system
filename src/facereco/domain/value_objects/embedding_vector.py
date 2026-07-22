"""Vecteur d'empreinte faciale — normalisé L2 systématiquement avant stockage (§6.1).

La normalisation L2 en amont rend la similarité cosinus équivalente à un simple
produit scalaire, ce qui permet l'usage d'un index optimisé (HNSW) et rend les
scores directement comparables entre deux requêtes. Mélanger des vecteurs
normalisés et non normalisés dans le même index invaliderait tous les scores.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

EMBEDDING_DIMENSION = 512
_L2_NORM_TOLERANCE = 1e-3


@dataclass(frozen=True, slots=True)
class EmbeddingVector:
    """Vecteur dense de dimension fixe, garanti normalisé L2 (norme ≈ 1.0)."""

    values: tuple[float, ...]

    def __post_init__(self) -> None:
        if len(self.values) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"EmbeddingVector doit avoir {EMBEDDING_DIMENSION} dimensions, "
                f"reçu {len(self.values)}."
            )
        norm = math.sqrt(sum(v * v for v in self.values))
        if abs(norm - 1.0) > _L2_NORM_TOLERANCE:
            raise ValueError(
                f"EmbeddingVector doit être normalisé L2 (norme={norm:.4f}, attendu ≈1.0)."
            )

    def cosine_similarity(self, other: EmbeddingVector) -> float:
        """Produit scalaire — équivaut à la similarité cosinus car les vecteurs sont normalisés."""
        return sum(a * b for a, b in zip(self.values, other.values, strict=True))

    @staticmethod
    def from_raw(raw: tuple[float, ...] | list[float]) -> EmbeddingVector:
        """Construit un EmbeddingVector à partir d'un vecteur brut, en le normalisant L2."""
        values = tuple(float(v) for v in raw)
        if len(values) != EMBEDDING_DIMENSION:
            raise ValueError(
                f"EmbeddingVector.from_raw attend {EMBEDDING_DIMENSION} dimensions, "
                f"reçu {len(values)}."
            )
        norm = math.sqrt(sum(v * v for v in values))
        if norm == 0.0:
            raise ValueError("Impossible de normaliser un vecteur nul.")
        return EmbeddingVector(values=tuple(v / norm for v in values))
