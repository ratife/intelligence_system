"""Use case du composant « Worker d'indexation » : traite une image, visage par visage.

Étapes (§6, figure 2) : chargement → détection → filtre qualité → embedding →
persistance idempotente. Un visage rejeté n'est jamais ignoré silencieusement :
il est tracé avec son motif (§6.1).
"""

from __future__ import annotations

from dataclasses import dataclass

from facereco.application.dto import IndexImageCommand
from facereco.domain.entities.event import IndexStatus
from facereco.domain.entities.face import FaceEmbedding
from facereco.domain.exceptions import EventNotFoundError
from facereco.domain.ports.clock import ClockPort
from facereco.domain.ports.event_repository import EventRepositoryPort
from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.domain.ports.face_embedding_repository import FaceEmbeddingRepositoryPort
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.domain.value_objects.quality import DEFAULT_QUALITY_THRESHOLDS, assess_face_quality


@dataclass(frozen=True, slots=True)
class ProcessImageResult:
    image_id: int
    faces_accepted: int
    faces_rejected: int


class ProcessImageMessageUseCase:
    def __init__(
        self,
        event_repository: EventRepositoryPort,
        object_storage: ObjectStoragePort,
        face_detector: FaceDetectorPort,
        face_embedder: FaceEmbedderPort,
        face_embedding_repository: FaceEmbeddingRepositoryPort,
        clock: ClockPort,
    ) -> None:
        self._event_repository = event_repository
        self._object_storage = object_storage
        self._face_detector = face_detector
        self._face_embedder = face_embedder
        self._face_embedding_repository = face_embedding_repository
        self._clock = clock

    def execute(self, command: IndexImageCommand) -> ProcessImageResult:
        image = self._event_repository.get_image(command.image_id)
        if image is None:
            raise EventNotFoundError(command.image_id)

        image_bytes = self._object_storage.get_image_bytes(image.storage_uri)
        detected_faces = self._face_detector.detect_faces(image_bytes)

        accepted: list[FaceEmbedding] = []
        rejected_count = 0

        for face_index, face in enumerate(detected_faces):
            assessment = assess_face_quality(
                bbox=face.bbox,
                detection_score=face.detection_score,
                sharpness=face.sharpness,
                yaw_degrees=face.yaw_degrees,
                thresholds=DEFAULT_QUALITY_THRESHOLDS,
            )
            if not assessment.passed:
                rejected_count += 1
                self._face_embedding_repository.record_rejected_face(
                    image_id=image.id,
                    face_index=face_index,
                    rejection_reason=assessment.rejection_reason or "inconnu",
                )
                continue

            embedding = self._face_embedder.compute_embedding(image_bytes, face)
            accepted.append(
                FaceEmbedding(
                    id=None,
                    image_id=image.id,
                    event_id=image.event_id,
                    face_index=face_index,
                    bbox=face.bbox,
                    detection_score=face.detection_score,
                    quality_score=face.detection_score,
                    embedding=embedding,
                    model_version=self._face_embedder.model_version,
                )
            )

        if accepted:
            self._face_embedding_repository.save_embeddings(accepted)

        self._event_repository.mark_image_index_status(
            image_id=image.id,
            status=IndexStatus.DONE,
            indexed_at=self._clock.now(),
        )

        return ProcessImageResult(
            image_id=image.id,
            faces_accepted=len(accepted),
            faces_rejected=rejected_count,
        )
