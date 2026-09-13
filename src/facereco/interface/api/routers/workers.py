"""Route de supervision de la file d'indexation — GET /api/v1/admin/workers.

Lecture seule : consommateurs enregistrés, retard de la file, rebuts. Authentifiée
comme le reste de l'API.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from facereco.application.use_cases.get_indexing_queue_status import (
    GetIndexingQueueStatusUseCase,
)
from facereco.interface.api.deps import get_current_actor_id, get_queue_status_use_case
from facereco.interface.api.schemas.workers import (
    QueueStatusResponseSchema,
    to_queue_status_response,
)

router = APIRouter(prefix="/api/v1/admin/workers", tags=["workers"])


@router.get("", response_model=QueueStatusResponseSchema)
async def get_workers(
    _actor_id: Annotated[str, Depends(get_current_actor_id)],
    use_case: Annotated[GetIndexingQueueStatusUseCase, Depends(get_queue_status_use_case)],
) -> QueueStatusResponseSchema:
    return to_queue_status_response(use_case.execute())
