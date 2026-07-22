"""Adapter d'embedding facial — ArcFace R100 (buffalo_l) via InsightFace/ONNX Runtime (ADR 003).

Le modèle de reconnaissance InsightFace effectue lui-même l'alignement 112×112
à partir des 5 points de repère (`face_align.norm_crop`), garantissant le même
pré-traitement que celui utilisé pour le calcul de netteté côté détection.
"""

from __future__ import annotations

from types import SimpleNamespace

import numpy as np

from facereco.domain.entities.face import DetectedFace
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.domain.value_objects.embedding_vector import EmbeddingVector
from facereco.domain.value_objects.model_version import ModelVersion
from facereco.infrastructure.ml.model_registry import load_model_by_taskname
from facereco.infrastructure.ml.preprocessing import decode_image


class ArcFaceEmbedder(FaceEmbedderPort):
    def __init__(
        self,
        model_pack: str = "buffalo_l",
        providers: list[str] | None = None,
        version: str = "arcface-r100-v1",
    ) -> None:
        self._model = load_model_by_taskname(
            model_pack, "recognition", providers or ["CPUExecutionProvider"]
        )
        self._model.prepare(ctx_id=0)
        self._version = ModelVersion(value=version)

    @property
    def model_version(self) -> ModelVersion:
        return self._version

    def compute_embedding(self, image_bytes: bytes, face: DetectedFace) -> EmbeddingVector:
        image = decode_image(image_bytes)
        kps = np.array(face.landmarks, dtype=np.float32)
        raw_embedding = self._model.get(image, SimpleNamespace(kps=kps))
        return EmbeddingVector.from_raw(raw_embedding.tolist())
