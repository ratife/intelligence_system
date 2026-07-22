"""Port de persistance pour les empreintes faciales."""

from __future__ import annotations

from abc import ABC, abstractmethod

from facereco.domain.entities.face import FaceEmbedding


class FaceEmbeddingRepositoryPort(ABC):
    @abstractmethod
    def save_embeddings(self, embeddings: list[FaceEmbedding]) -> None:
        """Persiste les empreintes de manière idempotente.

        Clé d'unicité : (image_id, model_version, face_index) — cf. P4. Un
        rejeu du même message ne doit jamais produire de doublon de vecteur.
        """
        raise NotImplementedError

    @abstractmethod
    def record_rejected_face(self, image_id: int, face_index: int, rejection_reason: str) -> None:
        """Trace un visage rejeté pour qualité (jamais ignoré silencieusement, §6.1)."""
        raise NotImplementedError
