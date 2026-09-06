"""Doublons en mémoire des ports du domaine, utilisés pour tester les use cases

sans aucune dépendance à Postgres, Redis, InsightFace ou S3.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from facereco.domain.entities.event import Event, EventImage, IndexStatus
from facereco.domain.entities.face import DetectedFace, FaceEmbedding
from facereco.domain.ports.audit_log import AuditLogPort
from facereco.domain.ports.clock import ClockPort
from facereco.domain.ports.event_catalog import EventCatalogPort
from facereco.domain.ports.event_repository import EventRepositoryPort
from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.domain.ports.face_embedding_repository import FaceEmbeddingRepositoryPort
from facereco.domain.ports.message_queue import MessageQueuePort, QueueMessage
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.domain.ports.quota import SearchQuotaPort
from facereco.domain.ports.vector_search import VectorSearchHit, VectorSearchPort
from facereco.domain.value_objects.embedding_vector import EMBEDDING_DIMENSION, EmbeddingVector
from facereco.domain.value_objects.event_catalog import EventCatalogPage, EventDetail
from facereco.domain.value_objects.model_version import ModelVersion


class FixedClock(ClockPort):
    def __init__(self, fixed: datetime) -> None:
        self._fixed = fixed

    def now(self) -> datetime:
        return self._fixed


@dataclass
class FakeEventRepository(EventRepositoryPort):
    events: dict[int, Event] = field(default_factory=dict)
    images: dict[int, EventImage] = field(default_factory=dict)
    status_updates: list[tuple[int, IndexStatus]] = field(default_factory=list)

    def get_event(self, event_id: int) -> Event | None:
        return self.events.get(event_id)

    def get_events_by_ids(self, event_ids: list[int]) -> dict[int, Event]:
        return {eid: self.events[eid] for eid in event_ids if eid in self.events}

    def get_image(self, image_id: int) -> EventImage | None:
        return self.images.get(image_id)

    def list_images_needing_indexing(
        self, model_version: ModelVersion, limit: int
    ) -> list[EventImage]:
        pending = [img for img in self.images.values() if img.needs_indexing()]
        return pending[:limit]

    def mark_image_index_status(
        self, image_id: int, status: IndexStatus, indexed_at: datetime | None
    ) -> None:
        self.status_updates.append((image_id, status))
        image = self.images[image_id]
        self.images[image_id] = EventImage(
            id=image.id,
            event_id=image.event_id,
            storage_uri=image.storage_uri,
            content_hash=image.content_hash,
            width=image.width,
            height=image.height,
            index_status=status,
            indexed_at=indexed_at,
        )


class FakeObjectStorage(ObjectStoragePort):
    def __init__(self) -> None:
        self.images: dict[str, bytes] = {}

    def get_image_bytes(self, storage_uri: str) -> bytes:
        return self.images[storage_uri]

    def build_signed_url(self, storage_uri: str, expires_in_seconds: int = 300) -> str:
        return f"https://signed.example/{storage_uri}?exp={expires_in_seconds}"


class ScriptedFaceDetector(FaceDetectorPort):
    """Retourne une liste de visages pré-définie, indépendamment du contenu de l'image."""

    def __init__(self, faces_by_image: dict[bytes, list[DetectedFace]]) -> None:
        self._faces_by_image = faces_by_image

    def detect_faces(self, image_bytes: bytes) -> list[DetectedFace]:
        return self._faces_by_image.get(image_bytes, [])


class DeterministicFaceEmbedder(FaceEmbedderPort):
    """Produit un embedding déterministe dérivé du hash de l'image — pas de vrai modèle ML."""

    def __init__(self, version: str = "fake-embedder-v1") -> None:
        self._version = ModelVersion(value=version)

    @property
    def model_version(self) -> ModelVersion:
        return self._version

    def compute_embedding(self, image_bytes: bytes, face: DetectedFace) -> EmbeddingVector:
        seed = (hash(image_bytes) ^ hash(face.bbox.as_tuple())) & 0xFFFFFFFF
        values = [0.0] * EMBEDDING_DIMENSION
        values[seed % EMBEDDING_DIMENSION] = 1.0
        return EmbeddingVector(values=tuple(values))


@dataclass
class FakeFaceEmbeddingRepository(FaceEmbeddingRepositoryPort):
    saved: list[FaceEmbedding] = field(default_factory=list)
    rejected: list[tuple[int, int, str]] = field(default_factory=list)

    def save_embeddings(self, embeddings: list[FaceEmbedding]) -> None:
        self.saved.extend(embeddings)

    def record_rejected_face(self, image_id: int, face_index: int, rejection_reason: str) -> None:
        self.rejected.append((image_id, face_index, rejection_reason))


@dataclass
class FakeMessageQueue(MessageQueuePort):
    published: list[int] = field(default_factory=list)
    acked: list[str] = field(default_factory=list)
    dead_lettered: list[tuple[str, str]] = field(default_factory=list)

    def publish_image_for_indexing(self, image_id: int) -> None:
        self.published.append(image_id)

    def read_pending(self, consumer_name: str, count: int) -> list[QueueMessage]:
        return []

    def acknowledge(self, message: QueueMessage) -> None:
        self.acked.append(message.message_id)

    def dead_letter(self, message: QueueMessage, reason: str) -> None:
        self.dead_lettered.append((message.message_id, reason))


@dataclass
class ScriptedVectorSearch(VectorSearchPort):
    hits: list[VectorSearchHit] = field(default_factory=list)

    def search_top_k(
        self,
        query: EmbeddingVector,
        model_version: ModelVersion,
        top_k: int,
        min_quality_score: float,
        date_from: date | None = None,
        date_to: date | None = None,
    ) -> list[VectorSearchHit]:
        return self.hits[:top_k]


@dataclass
class FakeAuditLog(AuditLogPort):
    records: list[dict] = field(default_factory=list)

    def record_search(
        self,
        actor_id: str,
        query_hash: str,
        result_count: int,
        top_score: float | None,
        threshold_used: float,
        model_version: ModelVersion,
    ) -> None:
        self.records.append(
            {
                "actor_id": actor_id,
                "query_hash": query_hash,
                "result_count": result_count,
                "top_score": top_score,
                "threshold_used": threshold_used,
                "model_version": str(model_version),
            }
        )


class AlwaysAllowQuota(SearchQuotaPort):
    def check_and_consume(self, actor_id: str) -> bool:
        return True


class AlwaysDenyQuota(SearchQuotaPort):
    def check_and_consume(self, actor_id: str) -> bool:
        return False


@dataclass
class ScriptedEventCatalog(EventCatalogPort):
    """Catalogue en mémoire : retient la version de modèle qu'on lui a demandée."""

    page: EventCatalogPage | None = None
    details: dict[int, EventDetail] = field(default_factory=dict)
    model_versions_seen: list[str] = field(default_factory=list)

    def list_events(self, model_version: ModelVersion, limit: int, offset: int) -> EventCatalogPage:
        self.model_versions_seen.append(str(model_version))
        return self.page or EventCatalogPage(events=(), total_count=0)

    def get_event_detail(self, event_id: int, model_version: ModelVersion) -> EventDetail | None:
        self.model_versions_seen.append(str(model_version))
        return self.details.get(event_id)
