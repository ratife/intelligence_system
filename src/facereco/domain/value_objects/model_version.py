"""Version du modèle d'embedding — versionnée comme du code (ADR 005).

Changer de modèle invalide tout l'index (les espaces vectoriels ne sont pas
compatibles entre eux) : toute empreinte est taguée avec la version qui l'a produite,
ce qui permet une réindexation sans coupure de service (double écriture puis bascule).
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class ModelVersion:
    """Identifiant opaque de version de modèle, ex. 'arcface-r100-v1'."""

    value: str

    def __post_init__(self) -> None:
        if not self.value.strip():
            raise ValueError("ModelVersion ne peut pas être vide.")

    def __str__(self) -> str:
        return self.value
