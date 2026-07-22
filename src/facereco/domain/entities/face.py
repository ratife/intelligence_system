"""Entités liées aux visages : détection brute et empreinte persistée."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime

from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.domain.value_objects.embedding_vector import EmbeddingVector
from facereco.domain.value_objects.model_version import ModelVersion


@dataclass(frozen=True, slots=True)
class DetectedFace:
    """Sortie brute du détecteur pour un visage, avant filtrage qualité et embedding.

    Ne stocke jamais le visage recadré en clair (ADR 007) — uniquement les mesures
    nécessaires à l'évaluation qualité et à l'alignement.
    """

    bbox: BoundingBox
    detection_score: float
    sharpness: float
    yaw_degrees: float
    landmarks: tuple[tuple[float, float], ...]


@dataclass(frozen=True, slots=True)
class FaceEmbedding:
    """Empreinte faciale persistée : un visage détecté, filtré qualité et vectorisé.

    Clé d'idempotence : (image_id, model_version, face_index) — cf. P4 du cadrage
    technique. Un rejeu de message ne doit jamais créer de doublon de vecteur.
    """

    id: int | None
    image_id: int
    event_id: int
    face_index: int
    bbox: BoundingBox
    detection_score: float
    quality_score: float
    embedding: EmbeddingVector
    model_version: ModelVersion
    cluster_id: int | None = None
    created_at: datetime | None = None

    def idempotency_key(self) -> tuple[int, str, int]:
        return (self.image_id, str(self.model_version), self.face_index)
