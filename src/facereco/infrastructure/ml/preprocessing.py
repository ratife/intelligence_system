"""Pré-traitement d'image partagé entre détection et embedding.

Ce module est utilisé à l'identique par le worker d'indexation et par le
service de requête : toute divergence entre les deux chemins détruirait
silencieusement la précision (§5, « piège classique n°1 »).
"""

from __future__ import annotations

import cv2
import numpy as np
from insightface.utils import face_align

ALIGNED_FACE_SIZE = 112


def decode_image(image_bytes: bytes) -> np.ndarray:
    """Décode des octets JPEG/PNG en image BGR (format attendu par OpenCV/InsightFace)."""
    array = np.frombuffer(image_bytes, dtype=np.uint8)
    image = cv2.imdecode(array, cv2.IMREAD_COLOR)
    if image is None:
        raise ValueError("Image illisible ou corrompue.")
    return image


def align_face(image_bgr: np.ndarray, landmarks: tuple[tuple[float, float], ...]) -> np.ndarray:
    """Aligne un visage sur un carré 112×112 à partir de 5 points de repère (norm_crop ArcFace)."""
    kps = np.array(landmarks, dtype=np.float32)
    aligned: np.ndarray = face_align.norm_crop(
        image_bgr, landmark=kps, image_size=ALIGNED_FACE_SIZE
    )
    return aligned


def compute_sharpness(crop_bgr: np.ndarray) -> float:
    """Variance du Laplacien (§6.1) — un flou de bougé donne une valeur faible."""
    gray = cv2.cvtColor(crop_bgr, cv2.COLOR_BGR2GRAY)
    return float(cv2.Laplacian(gray, cv2.CV_64F).var())


def estimate_yaw_degrees(landmarks: tuple[tuple[float, float], ...]) -> float:
    """Estimation approximative du yaw à partir de la dissymétrie horizontale des 5 points.

    Heuristique légère (pas un modèle de pose 3D dédié) : suffisante pour filtrer
    les profils marqués (§6.1, seuil > 45°). Point d'extension si une précision
    supérieure est requise (modèle landmark_3d_68).
    """
    left_eye, right_eye, nose = landmarks[0], landmarks[1], landmarks[2]
    eye_center_x = (left_eye[0] + right_eye[0]) / 2.0
    eye_distance = abs(right_eye[0] - left_eye[0]) or 1.0
    offset_ratio = (nose[0] - eye_center_x) / eye_distance
    yaw = offset_ratio * 90.0
    return max(-90.0, min(90.0, yaw))
