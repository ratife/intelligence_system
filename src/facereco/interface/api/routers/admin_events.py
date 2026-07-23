"""Routes d'administration : créer un événement et lui importer/indexer des images.

Utilise `infrastructure.devtools.event_import`, qui contourne volontairement
les ports du Domain (voir son docstring) — ces routes sont un outil dev/démo
pour peupler l'environnement (interface web comprise), pas une fonctionnalité
de production : en production, `events` est un système externe pré-existant
(§2.1).
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from pydantic import BaseModel

from facereco.domain.entities.event import Event
from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.infrastructure.devtools.event_import import (
    ImportedImage,
    create_event,
    get_event,
    import_and_index_image,
    list_events,
)
from facereco.interface.api.deps import (
    get_current_actor_id,
    get_face_detector,
    get_face_embedder,
    get_object_storage,
)

router = APIRouter(prefix="/api/v1/admin/events", tags=["admin-events"])

MAX_IMAGES_PER_UPLOAD = 50
MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024


class EventSchema(BaseModel):
    id: int
    description: str
    event_date: date
    address: str


class CreateEventRequest(BaseModel):
    description: str
    event_date: date
    address: str


class ImportedImageSchema(BaseModel):
    filename: str
    image_id: int
    duplicate: bool
    faces_accepted: int
    faces_rejected: int


class ImportImagesResponse(BaseModel):
    event_id: int
    results: list[ImportedImageSchema]


def _to_schema(event: Event) -> EventSchema:
    return EventSchema(
        id=event.id,
        description=event.description,
        event_date=event.event_date,
        address=event.address,
    )


def _to_imported_schema(result: ImportedImage) -> ImportedImageSchema:
    return ImportedImageSchema(
        filename=result.filename,
        image_id=result.image_id,
        duplicate=result.duplicate,
        faces_accepted=result.faces_accepted,
        faces_rejected=result.faces_rejected,
    )


@router.get("", response_model=list[EventSchema])
async def list_all_events(
    _actor_id: Annotated[str, Depends(get_current_actor_id)],
) -> list[EventSchema]:
    return [_to_schema(event) for event in list_events()]


@router.post("", response_model=EventSchema, status_code=status.HTTP_201_CREATED)
async def create_new_event(
    _actor_id: Annotated[str, Depends(get_current_actor_id)],
    body: CreateEventRequest,
) -> EventSchema:
    event = create_event(body.description, body.event_date, body.address)
    return _to_schema(event)


@router.post("/{event_id}/images", response_model=ImportImagesResponse)
async def import_images(
    event_id: int,
    _actor_id: Annotated[str, Depends(get_current_actor_id)],
    face_detector: Annotated[FaceDetectorPort, Depends(get_face_detector)],
    face_embedder: Annotated[FaceEmbedderPort, Depends(get_face_embedder)],
    object_storage: Annotated[ObjectStoragePort, Depends(get_object_storage)],
    images: Annotated[list[UploadFile], File()],
) -> ImportImagesResponse:
    if get_event(event_id) is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail=f"Événement {event_id} introuvable."
        )
    if not images:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT, detail="Aucune image fournie."
        )
    if len(images) > MAX_IMAGES_PER_UPLOAD:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail=f"Maximum {MAX_IMAGES_PER_UPLOAD} images par envoi.",
        )

    payloads: list[tuple[str, bytes]] = []
    for image in images:
        image_bytes = await image.read()
        if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
            raise HTTPException(
                status_code=status.HTTP_413_CONTENT_TOO_LARGE,
                detail=f"{image.filename} dépasse la limite de 10 Mo.",
            )
        payloads.append((image.filename or "image", image_bytes))

    results = [
        _to_imported_schema(
            import_and_index_image(
                event_id, filename, image_bytes, face_detector, face_embedder, object_storage
            )
        )
        for filename, image_bytes in payloads
    ]
    return ImportImagesResponse(event_id=event_id, results=results)
