"""Composition root — câblage des adapters concrets derrière les ports du Domain.

C'est le seul endroit du code qui connaît à la fois les use cases (Application)
et les implémentations concrètes (Infrastructure). Les modèles ML lourds sont
instanciés une seule fois au démarrage (voir `main.py`, lifespan) et réutilisés
via `request.app.state` — jamais reconstruits par requête.
"""

from __future__ import annotations

from collections.abc import Iterator
from typing import Annotated

from fastapi import Depends, Header, HTTPException, Request, status
from sqlalchemy.orm import Session

from facereco.application.use_cases.get_system_statistics import GetSystemStatisticsUseCase
from facereco.application.use_cases.index_event_images import TriggerIndexingUseCase
from facereco.application.use_cases.process_image_message import ProcessImageMessageUseCase
from facereco.application.use_cases.search_by_face import SearchByFaceUseCase
from facereco.domain.ports.audit_log import AuditLogPort
from facereco.domain.ports.event_repository import EventRepositoryPort
from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.domain.ports.face_embedding_repository import FaceEmbeddingRepositoryPort
from facereco.domain.ports.message_queue import MessageQueuePort
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.domain.ports.quota import SearchQuotaPort
from facereco.domain.ports.statistics import StatisticsPort
from facereco.domain.ports.vector_search import VectorSearchPort
from facereco.domain.value_objects.model_version import ModelVersion
from facereco.infrastructure.audit.postgres_audit_log import PostgresAuditLog
from facereco.infrastructure.config.settings import settings
from facereco.infrastructure.db.event_repository_pg import PostgresEventRepository
from facereco.infrastructure.db.face_embedding_repository_pg import (
    PostgresFaceEmbeddingRepository,
)
from facereco.infrastructure.db.session import session_scope
from facereco.infrastructure.db.statistics_pg import PostgresStatisticsRepository
from facereco.infrastructure.db.vector_search_pgvector import PgVectorSearch
from facereco.infrastructure.system_clock import SystemClock


def get_db_session() -> Iterator[Session]:
    with session_scope() as session:
        yield session


DbSession = Annotated[Session, Depends(get_db_session)]


def get_face_detector(request: Request) -> FaceDetectorPort:
    return request.app.state.face_detector  # type: ignore[no-any-return]


def get_face_embedder(request: Request) -> FaceEmbedderPort:
    return request.app.state.face_embedder  # type: ignore[no-any-return]


def get_object_storage(request: Request) -> ObjectStoragePort:
    return request.app.state.object_storage  # type: ignore[no-any-return]


def get_message_queue(request: Request) -> MessageQueuePort:
    return request.app.state.message_queue  # type: ignore[no-any-return]


def get_search_quota(request: Request) -> SearchQuotaPort:
    return request.app.state.search_quota  # type: ignore[no-any-return]


def get_event_repository(session: DbSession) -> EventRepositoryPort:
    return PostgresEventRepository(session)


def get_face_embedding_repository(session: DbSession) -> FaceEmbeddingRepositoryPort:
    return PostgresFaceEmbeddingRepository(session)


def get_vector_search(session: DbSession) -> VectorSearchPort:
    return PgVectorSearch(session)


def get_audit_log(session: DbSession) -> AuditLogPort:
    return PostgresAuditLog(session)


def get_statistics_repository(session: DbSession) -> StatisticsPort:
    return PostgresStatisticsRepository(session)


def get_statistics_use_case(
    statistics: Annotated[StatisticsPort, Depends(get_statistics_repository)],
) -> GetSystemStatisticsUseCase:
    return GetSystemStatisticsUseCase(statistics=statistics)


def get_search_use_case(
    face_detector: Annotated[FaceDetectorPort, Depends(get_face_detector)],
    face_embedder: Annotated[FaceEmbedderPort, Depends(get_face_embedder)],
    vector_search: Annotated[VectorSearchPort, Depends(get_vector_search)],
    event_repository: Annotated[EventRepositoryPort, Depends(get_event_repository)],
    audit_log: Annotated[AuditLogPort, Depends(get_audit_log)],
    quota: Annotated[SearchQuotaPort, Depends(get_search_quota)],
) -> SearchByFaceUseCase:
    return SearchByFaceUseCase(
        face_detector=face_detector,
        face_embedder=face_embedder,
        vector_search=vector_search,
        event_repository=event_repository,
        audit_log=audit_log,
        quota=quota,
        ann_top_k=settings.ann_top_k,
    )


def get_process_image_use_case(
    event_repository: Annotated[EventRepositoryPort, Depends(get_event_repository)],
    object_storage: Annotated[ObjectStoragePort, Depends(get_object_storage)],
    face_detector: Annotated[FaceDetectorPort, Depends(get_face_detector)],
    face_embedder: Annotated[FaceEmbedderPort, Depends(get_face_embedder)],
    face_embedding_repository: Annotated[
        FaceEmbeddingRepositoryPort, Depends(get_face_embedding_repository)
    ],
) -> ProcessImageMessageUseCase:
    return ProcessImageMessageUseCase(
        event_repository=event_repository,
        object_storage=object_storage,
        face_detector=face_detector,
        face_embedder=face_embedder,
        face_embedding_repository=face_embedding_repository,
        clock=SystemClock(),
    )


def get_trigger_indexing_use_case(
    event_repository: Annotated[EventRepositoryPort, Depends(get_event_repository)],
    message_queue: Annotated[MessageQueuePort, Depends(get_message_queue)],
) -> TriggerIndexingUseCase:
    return TriggerIndexingUseCase(
        event_repository=event_repository,
        message_queue=message_queue,
        current_model_version=ModelVersion(value=settings.model_version),
    )


def get_current_actor_id(
    authorization: Annotated[str, Header()],
    x_actor_id: Annotated[str, Header()],
) -> str:
    scheme, _, token = authorization.partition(" ")
    if scheme.lower() != "bearer" or token != settings.api_bearer_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="Authentification invalide."
        )
    if not x_actor_id.strip():
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED, detail="En-tête X-Actor-Id requis."
        )
    return x_actor_id
