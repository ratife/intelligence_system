"""Entités racines existantes : Event et EventImage.

La reconnaissance faciale est une couche d'enrichissement d'un modèle de données
préexistant (§2.1) — Event n'est pas redéfini, seulement complété par un statut
d'indexation sur ses images.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime
from enum import StrEnum


class IndexStatus(StrEnum):
    """Statut d'indexation d'une image d'événement pour une version de modèle donnée."""

    PENDING = "pending"
    DONE = "done"
    FAILED = "failed"
    SKIPPED = "skipped"


@dataclass(frozen=True, slots=True)
class Event:
    """Événement : titre, description, date, adresse — entité racine existante.

    `title` est l'intitulé court, celui que portent les listes, l'en-tête de la
    fiche et les résultats de recherche ; `description` est le texte libre, et
    peut être vide. Les deux étaient auparavant confondus dans `description`,
    qui devait à la fois nommer et décrire — plus elle décrivait, moins elle
    nommait.
    """

    id: int
    title: str
    description: str
    event_date: date
    address: str


@dataclass(frozen=True, slots=True)
class EventImage:
    """Une image associée à un événement, avec son statut d'indexation courant."""

    id: int
    event_id: int
    storage_uri: str
    content_hash: str
    width: int
    height: int
    index_status: IndexStatus
    indexed_at: datetime | None = None

    def needs_indexing(self) -> bool:
        return self.index_status in (IndexStatus.PENDING, IndexStatus.FAILED)
