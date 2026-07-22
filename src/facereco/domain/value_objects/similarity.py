"""Score de similarité cosinus entre deux empreintes faciales normalisées L2.

Le seuil n'est pas une constante théorique : il doit être calibré sur des données
réelles (cf. §10.2 du cadrage technique — protocole de calibration DET/FAR/FRR).
DEFAULT_SIMILARITY_THRESHOLD n'est qu'un point de départ ("équilibré") tant que la
calibration client n'a pas été réalisée.
"""

from __future__ import annotations

from dataclasses import dataclass

DEFAULT_SIMILARITY_THRESHOLD = 0.38


@dataclass(frozen=True, slots=True)
class SimilarityScore:
    """Score de similarité cosinus, compris entre -1.0 et 1.0."""

    value: float

    def __post_init__(self) -> None:
        if not -1.0 <= self.value <= 1.0:
            raise ValueError(f"SimilarityScore doit être dans [-1.0, 1.0], reçu {self.value}.")

    def meets_threshold(self, threshold: float) -> bool:
        return self.value >= threshold

    def __float__(self) -> float:
        return self.value
