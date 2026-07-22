"""Port d'entrée pour le calcul d'empreintes faciales — implémenté en Infrastructure (ArcFace)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from facereco.domain.entities.face import DetectedFace
from facereco.domain.value_objects.embedding_vector import EmbeddingVector
from facereco.domain.value_objects.model_version import ModelVersion


class FaceEmbedderPort(ABC):
    """Calcule l'empreinte vectorielle (embedding) d'un visage détecté.

    L'implémentation aligne le visage (112×112) et normalise L2 le vecteur
    produit avant de le retourner : le domaine reçoit toujours un
    EmbeddingVector déjà valide et comparable.
    """

    @property
    @abstractmethod
    def model_version(self) -> ModelVersion:
        """Version du modèle d'embedding utilisée — à taguer sur chaque empreinte produite."""
        raise NotImplementedError

    @abstractmethod
    def compute_embedding(self, image_bytes: bytes, face: DetectedFace) -> EmbeddingVector:
        raise NotImplementedError
