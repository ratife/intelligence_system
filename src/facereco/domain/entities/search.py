"""Entités du pipeline de recherche : passage du visage requête aux événements retrouvés."""

from __future__ import annotations

from dataclasses import dataclass

from facereco.domain.entities.event import Event
from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.domain.value_objects.model_version import ModelVersion


@dataclass(frozen=True, slots=True)
class SearchQueryInfo:
    """Métadonnées du visage requête effectivement utilisé pour la recherche."""

    faces_detected: int
    face_used_index: int
    face_used_bbox: BoundingBox
    face_used_quality: float
    model_version: ModelVersion


@dataclass(frozen=True, slots=True)
class FaceEvidence:
    """Preuve d'un match : l'image et la zone de visage permettant une vérification humaine.

    Le système ne présente jamais un score seul (P5/ADR010) — toujours accompagné
    de la preuve visuelle qui l'a produit.
    """

    image_id: int
    storage_uri: str
    bbox: BoundingBox
    similarity: float


@dataclass(frozen=True, slots=True)
class FaceCandidate:
    """Un visage candidat retourné par la recherche ANN, avant agrégation par événement."""

    event: Event
    similarity: float
    evidence: FaceEvidence


@dataclass(frozen=True, slots=True)
class EventMatch:
    """Un événement candidat, avec son score agrégé et sa preuve du meilleur visage."""

    event: Event
    confidence: float
    match_count: int
    evidence: FaceEvidence


@dataclass(frozen=True, slots=True)
class SearchResult:
    """Résultat complet d'une recherche par visage, classé par confiance décroissante."""

    query_info: SearchQueryInfo
    threshold_used: float
    matches: tuple[EventMatch, ...]
