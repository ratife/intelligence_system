"""Adapter de détection de visages — SCRFD via InsightFace/ONNX Runtime (ADR 003)."""

from __future__ import annotations

from facereco.domain.entities.face import DetectedFace
from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.infrastructure.ml.model_registry import load_model_by_taskname
from facereco.infrastructure.ml.preprocessing import (
    align_face,
    compute_sharpness,
    decode_image,
    estimate_yaw_degrees,
)

DEFAULT_DETECTION_INPUT_SIZE = (640, 640)


def clamp_bbox_to_image(
    x1: float, y1: float, x2: float, y2: float, image_width: int, image_height: int
) -> BoundingBox:
    """Ramène un cadre SCRFD dans les limites de l'image.

    SCRFD extrapole : un visage qui touche le bord du cadrage produit des
    coordonnées négatives ou débordant de l'image. `BoundingBox` refuse ces
    valeurs — à raison, puisque le cadre sert ensuite à découper le visage et à
    le dessiner sur l'image de preuve. La conversion est donc la responsabilité
    de cet adapter, pas un invariant à relâcher côté Domain.

    Sans ce recadrage, toute photo avec un visage au bord échouait trois fois
    puis partait en file de rebut, en restant « en attente » indéfiniment.
    """
    left = min(max(int(x1), 0), max(image_width - 1, 0))
    top = min(max(int(y1), 0), max(image_height - 1, 0))
    right = min(max(int(x2), left + 1), image_width)
    bottom = min(max(int(y2), top + 1), image_height)
    return BoundingBox(x=left, y=top, width=right - left, height=bottom - top)


class InsightFaceDetector(FaceDetectorPort):
    def __init__(self, model_pack: str = "buffalo_l", providers: list[str] | None = None) -> None:
        self._model = load_model_by_taskname(
            model_pack, "detection", providers or ["CPUExecutionProvider"]
        )
        self._model.prepare(ctx_id=0, input_size=DEFAULT_DETECTION_INPUT_SIZE)

    def detect_faces(self, image_bytes: bytes) -> list[DetectedFace]:
        image = decode_image(image_bytes)
        image_height, image_width = image.shape[:2]
        boxes, keypoints = self._model.detect(image, max_num=0)

        detected: list[DetectedFace] = []
        for i in range(boxes.shape[0]):
            x1, y1, x2, y2, det_score = boxes[i]
            landmarks = tuple((float(x), float(y)) for x, y in keypoints[i])
            aligned_crop = align_face(image, landmarks)
            detected.append(
                DetectedFace(
                    bbox=clamp_bbox_to_image(x1, y1, x2, y2, image_width, image_height),
                    detection_score=float(det_score),
                    sharpness=compute_sharpness(aligned_crop),
                    yaw_degrees=estimate_yaw_degrees(landmarks),
                    landmarks=landmarks,
                )
            )
        return detected
