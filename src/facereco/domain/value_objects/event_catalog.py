"""Catalogue d'événements — modèle de lecture pour parcourir ce qui est indexé.

Répond à une question que ni le tableau de bord ni la recherche ne couvrent :
« qu'est-ce que le système a réellement indexé, événement par événement, et
qu'a-t-il écarté ? ». Le tableau de bord agrège tout le système en un seul
chiffre ; la recherche part d'une photo. Entre les deux, il manquait de quoi
inspecter un événement.

Comme pour `SystemStatistics`, les compteurs bruts viennent de l'infrastructure
et les **taux** sont calculés ici, sur les mêmes dénominateurs (`read_rate`) —
un taux de rejet ne doit pas signifier autre chose selon l'écran qui l'affiche.

Périmètre assumé : ce modèle décrit l'état d'indexation, il n'identifie
personne. Les visages y sont désignés par leur position dans l'image
(`face_index`), jamais par une identité — le regroupement par personne est le
Lot 4, délibérément non implémenté.
"""

from __future__ import annotations

from dataclasses import dataclass

from facereco.domain.entities.event import Event, EventImage
from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.domain.value_objects.rates import read_rate


@dataclass(frozen=True, slots=True)
class IndexedFace:
    """Un visage retenu et vectorisé, tel qu'il est interrogeable en recherche."""

    face_index: int
    bbox: BoundingBox
    detection_score: float
    quality_score: float


@dataclass(frozen=True, slots=True)
class DiscardedFace:
    """Un visage détecté puis écarté par le filtre qualité (§6.1), avec son motif.

    Sans cette liste, une personne présente sur une photo mais introuvable en
    recherche resterait inexplicable. Le motif est la seule réponse possible.
    """

    face_index: int
    reason: str


@dataclass(frozen=True, slots=True)
class EventImageDetail:
    """Une image de l'événement, avec ce que l'indexation en a tiré."""

    image: EventImage
    indexed_faces: tuple[IndexedFace, ...]
    discarded_faces: tuple[DiscardedFace, ...]

    @property
    def detected_face_count(self) -> int:
        return len(self.indexed_faces) + len(self.discarded_faces)


@dataclass(frozen=True, slots=True)
class EventSummary:
    """Un événement et l'état d'indexation de ses images."""

    event: Event
    image_count: int
    indexed_image_count: int
    pending_image_count: int
    face_count: int
    discarded_face_count: int

    def __post_init__(self) -> None:
        counters = {
            "image_count": self.image_count,
            "indexed_image_count": self.indexed_image_count,
            "pending_image_count": self.pending_image_count,
            "face_count": self.face_count,
            "discarded_face_count": self.discarded_face_count,
        }
        for name, value in counters.items():
            if value < 0:
                raise ValueError(f"{name} ne peut pas être négatif, reçu {value}.")
        # Même garde que `SystemStatistics` : un sous-ensemble plus grand que son
        # ensemble signale une requête d'agrégation fausse, mieux vaut le voir
        # tout de suite qu'afficher un avancement au-dessus de 100 %.
        if self.indexed_image_count > self.image_count:
            raise ValueError(
                f"indexed_image_count ({self.indexed_image_count}) dépasse "
                f"image_count ({self.image_count})."
            )

    @property
    def detected_face_count(self) -> int:
        """Visages détectés = retenus + écartés."""
        return self.face_count + self.discarded_face_count

    @property
    def indexing_completion_rate(self) -> float:
        """Part des images de l'événement dont l'indexation est terminée."""
        return read_rate(self.indexed_image_count, self.image_count)

    @property
    def quality_rejection_rate(self) -> float:
        """Part des visages *détectés* écartés — même dénominateur qu'au tableau de bord."""
        return read_rate(self.discarded_face_count, self.detected_face_count)

    @property
    def is_searchable(self) -> bool:
        """Un événement sans aucun visage retenu ne peut jamais ressortir d'une recherche.

        C'est le diagnostic utile de la liste : un événement peut être « indexé
        à 100 % » et rester introuvable si tous ses visages ont été écartés.
        """
        return self.face_count > 0


@dataclass(frozen=True, slots=True)
class EventDetail:
    """Un événement, ses compteurs, et le détail image par image."""

    summary: EventSummary
    images: tuple[EventImageDetail, ...]


@dataclass(frozen=True, slots=True)
class EventCatalogPage:
    """Une tranche de la liste des événements, située dans l'ensemble.

    `offset` fait partie de l'état, il n'est pas décoratif : sans lui,
    « reste-t-il des événements ? » ne peut pas être répondu. Comparer la taille
    de la tranche au total ferait dire à la dernière page qu'il en reste, parce
    qu'elle est plus petite que l'ensemble.
    """

    events: tuple[EventSummary, ...]
    total_count: int
    offset: int = 0

    def __post_init__(self) -> None:
        if self.total_count < 0:
            raise ValueError(f"total_count ne peut pas être négatif, reçu {self.total_count}.")
        if self.offset < 0:
            raise ValueError(f"offset ne peut pas être négatif, reçu {self.offset}.")
        if self.offset + len(self.events) > self.total_count:
            raise ValueError(
                f"{len(self.events)} événements à partir de {self.offset} dépassent "
                f"le total de {self.total_count}."
            )

    @property
    def has_more(self) -> bool:
        """Vrai s'il reste des événements après cette tranche."""
        return self.offset + len(self.events) < self.total_count
