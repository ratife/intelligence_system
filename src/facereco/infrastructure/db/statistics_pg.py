"""Implémentation PostgreSQL du port StatisticsPort — agrégats du tableau de bord."""

from __future__ import annotations

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

from facereco.domain.entities.event import IndexStatus
from facereco.domain.ports.statistics import StatisticsPort
from facereco.domain.value_objects.system_statistics import (
    RejectionReasonCount,
    SystemStatistics,
)
from facereco.infrastructure.db.models import (
    EventImageModel,
    EventModel,
    FaceEmbeddingModel,
    RejectedFaceModel,
    SearchAuditLogModel,
)


class PostgresStatisticsRepository(StatisticsPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def collect(self) -> SystemStatistics:
        return SystemStatistics(
            event_count=self._count(select(func.count()).select_from(EventModel)),
            image_count=self._count(select(func.count()).select_from(EventImageModel)),
            indexed_image_count=self._count_images_with_status(IndexStatus.DONE),
            pending_image_count=self._count_images_with_status(IndexStatus.PENDING),
            face_count=self._count(select(func.count()).select_from(FaceEmbeddingModel)),
            rejected_face_count=self._count(select(func.count()).select_from(RejectedFaceModel)),
            search_count=self._count(select(func.count()).select_from(SearchAuditLogModel)),
            empty_search_count=self._count(
                select(func.count())
                .select_from(SearchAuditLogModel)
                .where(SearchAuditLogModel.result_count == 0)
            ),
            distinct_actor_count=self._count(
                select(func.count(func.distinct(SearchAuditLogModel.actor_id)))
            ),
            average_top_score=self._average_top_score(),
            rejections_by_reason=self._rejections_by_reason(),
            model_versions=self._model_versions(),
        )

    def _count(self, statement: Select[tuple[int]]) -> int:
        return self._session.scalar(statement) or 0

    def _count_images_with_status(self, status: IndexStatus) -> int:
        return self._count(
            select(func.count())
            .select_from(EventImageModel)
            .where(EventImageModel.index_status == status.value)
        )

    def _average_top_score(self) -> float | None:
        """Moyenne sur les seules recherches ayant trouvé quelque chose.

        `top_score` est NULL quand aucun événement ne dépasse le seuil ; AVG les
        ignore déjà, mais on l'écrit explicitement pour que le dénominateur soit
        lisible : c'est la confiance moyenne *des recherches abouties*, pas de
        toutes les recherches.
        """
        average = self._session.scalar(
            select(func.avg(SearchAuditLogModel.top_score)).where(
                SearchAuditLogModel.top_score.is_not(None)
            )
        )
        return float(average) if average is not None else None

    def _rejections_by_reason(self) -> tuple[RejectionReasonCount, ...]:
        rows = self._session.execute(
            select(RejectedFaceModel.rejection_reason, func.count())
            .group_by(RejectedFaceModel.rejection_reason)
            .order_by(func.count().desc())
        ).all()
        return tuple(RejectionReasonCount(reason=reason, count=count) for reason, count in rows)

    def _model_versions(self) -> tuple[str, ...]:
        """Versions de modèle présentes en base — plusieurs signalent une migration en cours."""
        rows = self._session.scalars(
            select(FaceEmbeddingModel.model_version)
            .distinct()
            .order_by(FaceEmbeddingModel.model_version)
        ).all()
        return tuple(rows)
