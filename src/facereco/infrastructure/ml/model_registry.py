"""Résolution des modèles ONNX individuels d'un pack InsightFace.

`insightface.app.FaceAnalysis` est un assemblage pratique mais impose la
présence d'un modèle de détection même quand on ne veut que la reconnaissance
(`assert 'detection' in self.models`). Le Domain expose deux ports distincts
(FaceDetectorPort, FaceEmbedderPort) qui doivent pouvoir être servis
indépendamment : ce module charge donc directement le fichier ONNX voulu via
`model_zoo.get_model`, en réutilisant l'utilitaire de téléchargement du pack.
"""

from __future__ import annotations

import glob
import os.path as osp
from typing import Any

from insightface.model_zoo import model_zoo
from insightface.utils import ensure_available


def load_model_by_taskname(model_pack: str, taskname: str, providers: list[str]) -> Any:
    model_dir = ensure_available("models", model_pack, root="~/.insightface")
    for onnx_file in sorted(glob.glob(osp.join(model_dir, "*.onnx"))):
        model = model_zoo.get_model(onnx_file, providers=providers)
        if model is not None and model.taskname == taskname:
            return model
    raise RuntimeError(f"Aucun modèle de type '{taskname}' trouvé dans le pack '{model_pack}'.")
