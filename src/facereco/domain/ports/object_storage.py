"""Port de stockage objet pour les images sources (S3/MinIO)."""

from __future__ import annotations

from abc import ABC, abstractmethod


class ObjectStoragePort(ABC):
    @abstractmethod
    def get_image_bytes(self, storage_uri: str) -> bytes:
        raise NotImplementedError

    @abstractmethod
    def build_signed_url(self, storage_uri: str, expires_in_seconds: int = 300) -> str:
        """URL signée à courte durée de vie — jamais d'accès direct au stockage (§12)."""
        raise NotImplementedError
