"""Port d'entrée pour la détection de visages — implémenté en Infrastructure (SCRFD)."""

from __future__ import annotations

from abc import ABC, abstractmethod

from facereco.domain.entities.face import DetectedFace


class FaceDetectorPort(ABC):
    """Détecte les visages présents dans une image.

    L'implémentation Infrastructure DOIT être identique pour le pipeline
    d'indexation et le pipeline de recherche — toute divergence de
    pré-traitement détruit silencieusement la précision (§5, « piège classique
    n°1 »). C'est la raison d'être de ce port unique partagé par les deux use cases.
    """

    @abstractmethod
    def detect_faces(self, image_bytes: bytes) -> list[DetectedFace]:
        """Retourne les visages détectés, sans filtrage qualité (appliqué en aval)."""
        raise NotImplementedError
