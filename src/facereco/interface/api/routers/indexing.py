"""Route d'administration : déclenche le scan des images à (ré)indexer.

En production, ce déclenchement est typiquement un job planifié ou un
LISTEN/NOTIFY Postgres (§5, composant « Scanner / CDC ») — exposé ici comme
endpoint HTTP pour la simplicité de la démonstration et des tests e2e.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from facereco.application.dto import TriggerIndexingCommand
from facereco.application.use_cases.index_event_images import TriggerIndexingUseCase
from facereco.interface.api.deps import get_current_actor_id, get_trigger_indexing_use_case

router = APIRouter(prefix="/api/v1/admin/indexing", tags=["indexing"])


class TriggerIndexingResponse(BaseModel):
    images_published: int


@router.post("/trigger", response_model=TriggerIndexingResponse)
async def trigger_indexing(
    _actor_id: Annotated[str, Depends(get_current_actor_id)],
    use_case: Annotated[TriggerIndexingUseCase, Depends(get_trigger_indexing_use_case)],
    batch_limit: int = 500,
) -> TriggerIndexingResponse:
    result = use_case.execute(TriggerIndexingCommand(batch_limit=batch_limit))
    return TriggerIndexingResponse(images_published=result.images_published)
