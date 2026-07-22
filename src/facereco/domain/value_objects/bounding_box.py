"""Value object représentant la zone rectangulaire d'un visage détecté dans une image."""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class BoundingBox:
    """Rectangle englobant en pixels, coin haut-gauche (x, y) + largeur/hauteur."""

    x: int
    y: int
    width: int
    height: int

    def __post_init__(self) -> None:
        if self.width <= 0 or self.height <= 0:
            raise ValueError("BoundingBox: width et height doivent être strictement positifs.")
        if self.x < 0 or self.y < 0:
            raise ValueError("BoundingBox: x et y doivent être positifs ou nuls.")

    @property
    def side(self) -> int:
        """Côté du carré équivalent — utilisé pour le filtrage qualité (taille minimale)."""
        return min(self.width, self.height)

    def as_tuple(self) -> tuple[int, int, int, int]:
        return (self.x, self.y, self.width, self.height)
