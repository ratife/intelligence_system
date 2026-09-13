"""Routes du catalogue d'événements — GET /api/v1/events et /api/v1/events/{id}.

À ne pas confondre avec `/api/v1/admin/events` : celles-là *créent* des
événements et importent des images en contournant les ports (outillage dev/démo,
cf. `devtools/event_import.py`). Celles-ci sont en lecture seule et passent par
la couture complète (`EventCatalogPort`), parce que consulter le catalogue est
une fonctionnalité produit.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends, Query

from facereco.application.dto import GetEventDetailCommand, ListEventsCommand
from facereco.application.use_cases.get_event_detail import GetEventDetailUseCase
from facereco.application.use_cases.list_events import ListEventsUseCase
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.interface.api.deps import (
    get_current_actor_id,
    get_event_detail_use_case,
    get_list_events_use_case,
    get_object_storage,
)
from facereco.interface.api.schemas.events import (
    EventDetailResponseSchema,
    EventListResponseSchema,
    to_event_detail_response,
    to_event_list_response,
)

router = APIRouter(prefix="/api/v1/events", tags=["events"])

MAX_PAGE_SIZE = 200


@router.get("", response_model=EventListResponseSchema)
async def list_events(
    _actor_id: Annotated[str, Depends(get_current_actor_id)],
    use_case: Annotated[ListEventsUseCase, Depends(get_list_events_use_case)],
    limit: Annotated[int, Query(ge=1, le=MAX_PAGE_SIZE)] = 50,
    offset: Annotated[int, Query(ge=0)] = 0,
) -> EventListResponseSchema:
    """Les événements les plus récents d'abord, avec leur état d'indexation."""
    page = use_case.execute(ListEventsCommand(limit=limit, offset=offset))
    return to_event_list_response(page)


@router.get("/{event_id}", response_model=EventDetailResponseSchema)
async def get_event_detail(
    event_id: int,
    _actor_id: Annotated[str, Depends(get_current_actor_id)],
    use_case: Annotated[GetEventDetailUseCase, Depends(get_event_detail_use_case)],
    object_storage: Annotated[ObjectStoragePort, Depends(get_object_storage)],
) -> EventDetailResponseSchema:
    """Détail image par image : visages retenus, visages écartés et leur motif.

    Les URLs signées expirent en quelques minutes : elles sont valables le temps
    de consulter la page, pas d'être partagées.
    """
    detail = use_case.execute(GetEventDetailCommand(event_id=event_id))
    image_urls = {
        item.image.id: object_storage.build_signed_url(item.image.storage_uri)
        for item in detail.images
    }
    return to_event_detail_response(detail, image_urls)
