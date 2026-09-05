"""Schemas Pydantic du tableau de bord — distincts du value object du Domain.

Les taux dérivés sont exposés **calculés** plutôt que laissés à l'appelant : ils
portent des choix de dénominateur (cf. `system_statistics.py`) qu'une interface
ne doit pas avoir à redevinner, et qui doivent rester cohérents entre clients.
"""

from __future__ import annotations

from pydantic import BaseModel

from facereco.domain.value_objects.system_statistics import SystemStatistics


class RejectionReasonSchema(BaseModel):
    reason: str
    count: int


class StatisticsResponseSchema(BaseModel):
    event_count: int
    image_count: int
    indexed_image_count: int
    pending_image_count: int
    face_count: int
    rejected_face_count: int
    detected_face_count: int
    search_count: int
    empty_search_count: int
    distinct_actor_count: int
    average_top_score: float | None
    indexing_completion_rate: float
    quality_rejection_rate: float
    average_faces_per_indexed_image: float
    empty_search_rate: float
    rejections_by_reason: list[RejectionReasonSchema]
    model_versions: list[str]


def to_statistics_response(statistics: SystemStatistics) -> StatisticsResponseSchema:
    return StatisticsResponseSchema(
        event_count=statistics.event_count,
        image_count=statistics.image_count,
        indexed_image_count=statistics.indexed_image_count,
        pending_image_count=statistics.pending_image_count,
        face_count=statistics.face_count,
        rejected_face_count=statistics.rejected_face_count,
        detected_face_count=statistics.detected_face_count,
        search_count=statistics.search_count,
        empty_search_count=statistics.empty_search_count,
        distinct_actor_count=statistics.distinct_actor_count,
        average_top_score=statistics.average_top_score,
        indexing_completion_rate=statistics.indexing_completion_rate,
        quality_rejection_rate=statistics.quality_rejection_rate,
        average_faces_per_indexed_image=statistics.average_faces_per_indexed_image,
        empty_search_rate=statistics.empty_search_rate,
        rejections_by_reason=[
            RejectionReasonSchema(reason=item.reason, count=item.count)
            for item in statistics.rejections_by_reason
        ],
        model_versions=list(statistics.model_versions),
    )
