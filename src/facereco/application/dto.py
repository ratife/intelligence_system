"""DTO applicatifs — distincts des schemas HTTP (Interface) et des modèles ORM (Infrastructure).

Ils transportent l'intention de l'appelant vers les use cases, indépendamment
du protocole de transport (HTTP, CLI, message de queue, ...).
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date


@dataclass(frozen=True, slots=True)
class SearchByFaceCommand:
    """Intention de recherche : image requête + filtres optionnels."""

    actor_id: str
    query_image_bytes: bytes
    face_index: int | None = None
    threshold: float | None = None
    date_from: date | None = None
    date_to: date | None = None
    limit: int = 20


@dataclass(frozen=True, slots=True)
class IndexImageCommand:
    """Intention d'indexer une image d'événement précise (issue d'un message de queue)."""

    image_id: int


@dataclass(frozen=True, slots=True)
class TriggerIndexingCommand:
    """Intention de scanner les images en attente d'indexation et de les publier en file."""

    batch_limit: int = 500
