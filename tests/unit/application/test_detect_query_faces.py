"""Le use case qui rend `face_index` intelligible avant toute recherche."""

from __future__ import annotations

from facereco.application.dto import DetectQueryFacesCommand
from facereco.application.use_cases.detect_query_faces import DetectQueryFacesUseCase
from facereco.domain.entities.face import DetectedFace
from facereco.domain.value_objects.bounding_box import BoundingBox

from .fakes import ScriptedFaceDetector

QUERY_IMAGE = b"query-jpeg-bytes"


def _face(x: int, score: float) -> DetectedFace:
    return DetectedFace(
        bbox=BoundingBox(x=x, y=0, width=100, height=100),
        detection_score=score,
        sharpness=100.0,
        yaw_degrees=0.0,
        landmarks=(),
    )


def _use_case(faces: list[DetectedFace]) -> DetectQueryFacesUseCase:
    return DetectQueryFacesUseCase(face_detector=ScriptedFaceDetector({QUERY_IMAGE: faces}))


def test_preserves_detector_order() -> None:
    """L'ordre *est* le contrat : la position sert d'index à `face_index`.

    Trier ou filtrer ici (par score, par taille) décalerait silencieusement les
    index et ferait chercher un autre visage que celui désigné à l'écran.
    """
    faces = [_face(x=0, score=0.42), _face(x=200, score=0.99), _face(x=400, score=0.71)]

    detected = _use_case(faces).execute(DetectQueryFacesCommand(query_image_bytes=QUERY_IMAGE))

    assert [face.bbox.x for face in detected] == [0, 200, 400]


def test_image_without_face_returns_empty_list_rather_than_raising() -> None:
    """« Que contient cette image ? » — « rien » est une réponse, pas une panne.

    C'est la recherche qui refuse une image sans visage (409) ; la détection
    préalable, elle, doit pouvoir le dire calmement pour que l'interface
    l'annonce sans passer par un écran d'erreur.
    """
    detected = _use_case([]).execute(DetectQueryFacesCommand(query_image_bytes=b"pas-une-photo"))

    assert detected == []
