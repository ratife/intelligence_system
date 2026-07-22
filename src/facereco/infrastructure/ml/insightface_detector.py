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


class InsightFaceDetector(FaceDetectorPort):
    def __init__(self, model_pack: str = "buffalo_l", providers: list[str] | None = None) -> None:
        self._model = load_model_by_taskname(
            model_pack, "detection", providers or ["CPUExecutionProvider"]
        )
        self._model.prepare(ctx_id=0, input_size=DEFAULT_DETECTION_INPUT_SIZE)

    def detect_faces(self, image_bytes: bytes) -> list[DetectedFace]:
        image = decode_image(image_bytes)
        boxes, keypoints = self._model.detect(image, max_num=0)

        detected: list[DetectedFace] = []
        for i in range(boxes.shape[0]):
            x1, y1, x2, y2, det_score = boxes[i]
            landmarks = tuple((float(x), float(y)) for x, y in keypoints[i])
            aligned_crop = align_face(image, landmarks)
            detected.append(
                DetectedFace(
                    bbox=BoundingBox(
                        x=int(x1),
                        y=int(y1),
                        width=max(int(x2 - x1), 1),
                        height=max(int(y2 - y1), 1),
                    ),
                    detection_score=float(det_score),
                    sharpness=compute_sharpness(aligned_crop),
                    yaw_degrees=estimate_yaw_degrees(landmarks),
                    landmarks=landmarks,
                )
            )
        return detected
