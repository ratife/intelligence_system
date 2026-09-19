"""Schemas Pydantic HTTP — sérialisation de réponse, distincts des entités du Domain."""

from __future__ import annotations

from collections.abc import Sequence
from datetime import date

from pydantic import BaseModel

from facereco.domain.entities.face import DetectedFace
from facereco.domain.entities.search import SearchResult


class QueryFaceSchema(BaseModel):
    """Un visage détecté dans l'image requête, situable dans l'image par son cadre.

    `bbox` est en pixels de l'image décodée, `[x, y, largeur, hauteur]` — c'est ce
    qui permet à un client de dessiner le cadre et de rendre `index` intelligible
    pour un humain, au lieu d'un simple numéro.
    """

    index: int
    bbox: list[int]
    quality: float


class QuerySchema(BaseModel):
    faces_detected: int
    face_used: QueryFaceSchema
    model_version: str


class QueryFacesResponseSchema(BaseModel):
    """Réponse de la détection préalable — aucune recherche n'a été effectuée."""

    faces_detected: int
    faces: list[QueryFaceSchema]


class EvidenceSchema(BaseModel):
    image_id: int
    image_url: str
    bbox: list[int]
    similarity: float


class EventMatchSchema(BaseModel):
    event_id: int
    title: str
    description: str
    event_date: date
    address: str
    confidence: float
    match_count: int
    evidence: EvidenceSchema


class SearchResponseSchema(BaseModel):
    query: QuerySchema
    threshold_used: float
    results: list[EventMatchSchema]


def to_query_faces_response(faces: Sequence[DetectedFace]) -> QueryFacesResponseSchema:
    """L'index exposé est la position dans la liste du détecteur — celle qu'attend `face_index`."""
    return QueryFacesResponseSchema(
        faces_detected=len(faces),
        faces=[
            QueryFaceSchema(
                index=index,
                bbox=list(face.bbox.as_tuple()),
                quality=face.detection_score,
            )
            for index, face in enumerate(faces)
        ],
    )


def to_search_response(result: SearchResult, evidence_urls: dict[int, str]) -> SearchResponseSchema:
    """Traduit le SearchResult du Domain en schema HTTP, en résolvant les URLs signées."""
    return SearchResponseSchema(
        query=QuerySchema(
            faces_detected=result.query_info.faces_detected,
            face_used=QueryFaceSchema(
                index=result.query_info.face_used_index,
                bbox=list(result.query_info.face_used_bbox.as_tuple()),
                quality=result.query_info.face_used_quality,
            ),
            model_version=str(result.query_info.model_version),
        ),
        threshold_used=result.threshold_used,
        results=[
            EventMatchSchema(
                event_id=match.event.id,
                title=match.event.title,
                description=match.event.description,
                event_date=match.event.event_date,
                address=match.event.address,
                confidence=match.confidence,
                match_count=match.match_count,
                evidence=EvidenceSchema(
                    image_id=match.evidence.image_id,
                    image_url=evidence_urls[match.evidence.image_id],
                    bbox=list(match.evidence.bbox.as_tuple()),
                    similarity=match.evidence.similarity,
                ),
            )
            for match in result.matches
        ],
    )
