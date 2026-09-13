"""Routes HTTP du pipeline de recherche — POST /api/v1/search/by-face (contrat §12).

Deux routes, une seule recherche : `/faces` se contente de détecter les visages
de l'image soumise pour que l'appelant puisse en désigner un ; `/by-face` fait la
recherche. Cf. `DetectQueryFacesUseCase` pour la raison de cette séparation.
"""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from facereco.application.dto import DetectQueryFacesCommand, SearchByFaceCommand
from facereco.application.use_cases.detect_query_faces import DetectQueryFacesUseCase
from facereco.application.use_cases.search_by_face import SearchByFaceUseCase
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.interface.api.deps import (
    get_current_actor_id,
    get_detect_query_faces_use_case,
    get_object_storage,
    get_search_use_case,
)
from facereco.interface.api.schemas.search import (
    QueryFacesResponseSchema,
    SearchResponseSchema,
    to_query_faces_response,
    to_search_response,
)

router = APIRouter(prefix="/api/v1/search", tags=["search"])

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
MAX_RESULTS_LIMIT = 100


async def _read_within_size_limit(image: UploadFile) -> bytes:
    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image dépassant la limite de 10 Mo.",
        )
    return image_bytes


@router.post("/faces", response_model=QueryFacesResponseSchema)
async def detect_query_faces(
    actor_id: Annotated[str, Depends(get_current_actor_id)],
    use_case: Annotated[DetectQueryFacesUseCase, Depends(get_detect_query_faces_use_case)],
    image: Annotated[UploadFile, File()],
) -> QueryFacesResponseSchema:
    """Situe les visages de l'image, sans rien chercher ni consulter d'index.

    L'authentification est exigée comme partout ; le quota de recherche, lui, ne
    s'applique pas — voir le use case pour le raisonnement.
    """
    image_bytes = await _read_within_size_limit(image)
    faces = use_case.execute(DetectQueryFacesCommand(query_image_bytes=image_bytes))
    return to_query_faces_response(faces)


@router.post("/by-face", response_model=SearchResponseSchema)
async def search_by_face(
    actor_id: Annotated[str, Depends(get_current_actor_id)],
    use_case: Annotated[SearchByFaceUseCase, Depends(get_search_use_case)],
    object_storage: Annotated[ObjectStoragePort, Depends(get_object_storage)],
    image: Annotated[UploadFile, File()],
    face_index: Annotated[int | None, Form()] = None,
    threshold: Annotated[float | None, Form()] = None,
    date_from: Annotated[date | None, Form()] = None,
    date_to: Annotated[date | None, Form()] = None,
    limit: Annotated[int, Form()] = 20,
) -> SearchResponseSchema:
    image_bytes = await _read_within_size_limit(image)

    command = SearchByFaceCommand(
        actor_id=actor_id,
        query_image_bytes=image_bytes,
        face_index=face_index,
        threshold=threshold,
        date_from=date_from,
        date_to=date_to,
        limit=min(limit, MAX_RESULTS_LIMIT),
    )
    result = use_case.execute(command)

    evidence_urls = {
        match.evidence.image_id: object_storage.build_signed_url(match.evidence.storage_uri)
        for match in result.matches
    }
    return to_search_response(result, evidence_urls)
