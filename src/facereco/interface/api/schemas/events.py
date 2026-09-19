"""Schemas HTTP du catalogue d'événements — GET /api/v1/events[/{id}].

`event_images.width/height` n'est volontairement pas exposé : ces colonnes sont
renseignées par PIL (`devtools/event_import.py`), qui n'applique pas
l'orientation EXIF, alors que les cadres de visages sont en coordonnées de
l'image décodée par OpenCV, qui l'applique. Les deux ne concordent pas pour une
photo pivotée. Un client mesure l'image qu'il affiche, c'est la seule source
fiable.
"""

from __future__ import annotations

from datetime import date, datetime

from pydantic import BaseModel

from facereco.domain.value_objects.event_catalog import (
    EventCatalogPage,
    EventDetail,
    EventSummary,
)


class EventSummarySchema(BaseModel):
    """Un événement et son état d'indexation, tel qu'il apparaît dans la liste."""

    id: int
    title: str
    description: str
    event_date: date
    address: str
    image_count: int
    indexed_image_count: int
    pending_image_count: int
    face_count: int
    discarded_face_count: int
    indexing_completion_rate: float
    quality_rejection_rate: float
    is_searchable: bool
    """Faux quand aucun visage n'a été retenu : l'événement ne peut pas ressortir
    d'une recherche, même indexé à 100 %."""


class EventListResponseSchema(BaseModel):
    events: list[EventSummarySchema]
    total_count: int
    offset: int
    has_more: bool


class IndexedFaceSchema(BaseModel):
    face_index: int
    bbox: list[int]
    """`[x, y, largeur, hauteur]` en pixels de l'image décodée."""

    detection_score: float
    quality_score: float


class DiscardedFaceSchema(BaseModel):
    face_index: int
    reason: str


class EventImageSchema(BaseModel):
    image_id: int
    image_url: str
    """URL signée à courte durée de vie (§12) — jamais l'URI de stockage brute."""

    index_status: str
    indexed_at: datetime | None
    indexed_faces: list[IndexedFaceSchema]
    discarded_faces: list[DiscardedFaceSchema]


class EventDetailResponseSchema(BaseModel):
    event: EventSummarySchema
    images: list[EventImageSchema]


def _to_summary(summary: EventSummary) -> EventSummarySchema:
    return EventSummarySchema(
        id=summary.event.id,
        title=summary.event.title,
        description=summary.event.description,
        event_date=summary.event.event_date,
        address=summary.event.address,
        image_count=summary.image_count,
        indexed_image_count=summary.indexed_image_count,
        pending_image_count=summary.pending_image_count,
        face_count=summary.face_count,
        discarded_face_count=summary.discarded_face_count,
        indexing_completion_rate=summary.indexing_completion_rate,
        quality_rejection_rate=summary.quality_rejection_rate,
        is_searchable=summary.is_searchable,
    )


def to_event_list_response(page: EventCatalogPage) -> EventListResponseSchema:
    return EventListResponseSchema(
        events=[_to_summary(summary) for summary in page.events],
        total_count=page.total_count,
        offset=page.offset,
        has_more=page.has_more,
    )


def to_event_detail_response(
    detail: EventDetail, image_urls: dict[int, str]
) -> EventDetailResponseSchema:
    """Traduit le détail du Domain, en résolvant les URLs signées des images."""
    return EventDetailResponseSchema(
        event=_to_summary(detail.summary),
        images=[
            EventImageSchema(
                image_id=item.image.id,
                image_url=image_urls[item.image.id],
                index_status=str(item.image.index_status),
                indexed_at=item.image.indexed_at,
                indexed_faces=[
                    IndexedFaceSchema(
                        face_index=face.face_index,
                        bbox=list(face.bbox.as_tuple()),
                        detection_score=face.detection_score,
                        quality_score=face.quality_score,
                    )
                    for face in item.indexed_faces
                ],
                discarded_faces=[
                    DiscardedFaceSchema(face_index=face.face_index, reason=face.reason)
                    for face in item.discarded_faces
                ],
            )
            for item in detail.images
        ],
    )
