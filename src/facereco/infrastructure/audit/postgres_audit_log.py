"""Implémentation PostgreSQL du port AuditLogPort — journal non désactivable (ADR 008)."""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy.orm import Session

from facereco.domain.ports.audit_log import AuditLogPort
from facereco.domain.value_objects.model_version import ModelVersion
from facereco.infrastructure.db.models import SearchAuditLogModel


class PostgresAuditLog(AuditLogPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def record_search(
        self,
        actor_id: str,
        query_hash: str,
        result_count: int,
        top_score: float | None,
        threshold_used: float,
        model_version: ModelVersion,
    ) -> None:
        self._session.add(
            SearchAuditLogModel(
                actor_id=actor_id,
                query_hash=query_hash,
                result_count=result_count,
                top_score=top_score,
                threshold_used=threshold_used,
                model_version=str(model_version),
                created_at=datetime.now(UTC),
            )
        )
