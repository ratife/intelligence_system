"""Route du tableau de bord — GET /api/v1/stats.

Lecture agrégée de l'état du système. Authentifiée comme le reste de l'API :
les volumétries d'un système de reconnaissance faciale ne sont pas publiques.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends

from facereco.application.use_cases.get_system_statistics import GetSystemStatisticsUseCase
from facereco.interface.api.deps import get_current_actor_id, get_statistics_use_case
from facereco.interface.api.schemas.statistics import (
    StatisticsResponseSchema,
    to_statistics_response,
)

router = APIRouter(prefix="/api/v1/stats", tags=["stats"])


@router.get("", response_model=StatisticsResponseSchema)
async def get_statistics(
    _actor_id: Annotated[str, Depends(get_current_actor_id)],
    use_case: Annotated[GetSystemStatisticsUseCase, Depends(get_statistics_use_case)],
) -> StatisticsResponseSchema:
    return to_statistics_response(use_case.execute())
