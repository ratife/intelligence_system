"""Route HTTP du pipeline de recherche — POST /api/v1/search/by-face (contrat §12)."""

from __future__ import annotations

from datetime import date
from typing import Annotated

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from facereco.application.dto import SearchByFaceCommand
from facereco.application.use_cases.search_by_face import SearchByFaceUseCase
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.interface.api.deps import (
    get_current_actor_id,
    get_object_storage,
    get_search_use_case,
)
from facereco.interface.api.schemas.search import SearchResponseSchema, to_search_response

router = APIRouter(prefix="/api/v1/search", tags=["search"])

MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024
MAX_RESULTS_LIMIT = 100


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
    image_bytes = await image.read()
    if len(image_bytes) > MAX_IMAGE_SIZE_BYTES:
        raise HTTPException(
            status_code=status.HTTP_413_CONTENT_TOO_LARGE,
            detail="Image dépassant la limite de 10 Mo.",
        )

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
