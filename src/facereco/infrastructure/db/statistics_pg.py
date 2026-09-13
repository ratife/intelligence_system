"""Implémentation PostgreSQL du port StatisticsPort — agrégats du tableau de bord."""

from __future__ import annotations

from sqlalchemy import Select, func, select, text
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
            rejected_face_count=self._discarded_face_count(),
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

    def _discarded_face_count(self) -> int:
        """Visages écartés distincts, et non lignes de `rejected_faces`.

        La table n'a pas de contrainte d'unicité, et une image dont *tous* les
        visages ont été écartés reste éligible à l'indexation (elle n'a aucune
        empreinte pour la version de modèle courante, donc
        `list_images_needing_indexing` la resélectionne) : chaque relance y
        réinsère les mêmes rejets. Compter les lignes brutes gonfle le taux de
        rejet — mesuré sur les données de développement, d'un facteur 3,75 — et
        rendrait inexploitable l'indicateur qui doit précisément servir à régler
        les seuils du filtre qualité (§6.1).

        Le dédoublonnage est un correctif de lecture, pas une réparation : la
        duplication en base reste à traiter (contrainte d'unicité, ou statut
        d'image distinguant « aucun visage retenu » de « à indexer »).
        """
        distinct_faces = (
            select(RejectedFaceModel.image_id, RejectedFaceModel.face_index).distinct().subquery()
        )
        return self._count(select(func.count()).select_from(distinct_faces))

    def _rejections_by_reason(self) -> tuple[RejectionReasonCount, ...]:
        """Un visage écarté compte une fois, sur son motif le plus ancien.

        Même dédoublonnage que `_discarded_face_count`, pour que la somme des
        motifs égale le total affiché à côté. Le motif retenu est celui du
        premier rejet : un rejeu ultérieur, à seuils identiques, ne dit rien de
        neuf.
        """
        first_rejections = text(
            """
            SELECT rejection_reason, count(*) AS total
            FROM (
                SELECT DISTINCT ON (image_id, face_index) rejection_reason
                FROM rejected_faces
                ORDER BY image_id, face_index, created_at
            ) premiers_rejets
            GROUP BY rejection_reason
            ORDER BY total DESC
            """
        )
        rows = self._session.execute(first_rejections).all()
        return tuple(
            RejectionReasonCount(reason=row.rejection_reason, count=row.total) for row in rows
        )

    def _model_versions(self) -> tuple[str, ...]:
        """Versions de modèle présentes en base — plusieurs signalent une migration en cours."""
        rows = self._session.scalars(
            select(FaceEmbeddingModel.model_version)
            .distinct()
            .order_by(FaceEmbeddingModel.model_version)
        ).all()
        return tuple(rows)
