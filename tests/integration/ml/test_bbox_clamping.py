"""Recadrage des cadres SCRFD débordant de l'image.

Régression réelle : les photos comportant un visage au bord du cadrage
échouaient à l'indexation (`BoundingBox: x et y doivent être positifs ou nuls`),
repassaient trois fois puis partaient en file de rebut, en restant « en
attente » indéfiniment.

Fonction pure : ni ONNX ni conteneur nécessaires, d'où l'absence de marqueur
`integration` malgré l'emplacement, choisi pour rester avec l'adapter testé.
"""

from __future__ import annotations

import pytest

from facereco.infrastructure.ml.insightface_detector import clamp_bbox_to_image

IMAGE_WIDTH = 640
IMAGE_HEIGHT = 480


def test_box_inside_the_image_is_left_untouched() -> None:
    bbox = clamp_bbox_to_image(100, 80, 200, 220, IMAGE_WIDTH, IMAGE_HEIGHT)

    assert bbox.as_tuple() == (100, 80, 100, 140)


def test_negative_origin_is_clamped_to_zero() -> None:
    """Le cas qui faisait planter : visage coupé par le bord haut-gauche."""
    bbox = clamp_bbox_to_image(-30, -12, 90, 110, IMAGE_WIDTH, IMAGE_HEIGHT)

    assert bbox.x == 0
    assert bbox.y == 0
    # Seule la partie visible est conservée.
    assert bbox.width == 90
    assert bbox.height == 110


def test_overflowing_far_edge_is_clamped_to_image_bounds() -> None:
    bbox = clamp_bbox_to_image(600, 440, 900, 700, IMAGE_WIDTH, IMAGE_HEIGHT)

    assert bbox.x + bbox.width <= IMAGE_WIDTH
    assert bbox.y + bbox.height <= IMAGE_HEIGHT
    assert bbox.as_tuple() == (600, 440, 40, 40)


def test_box_larger_than_the_image_is_reduced_to_the_image() -> None:
    bbox = clamp_bbox_to_image(-50, -50, 5000, 5000, IMAGE_WIDTH, IMAGE_HEIGHT)

    assert bbox.as_tuple() == (0, 0, IMAGE_WIDTH, IMAGE_HEIGHT)


def test_degenerate_box_keeps_a_strictly_positive_size() -> None:
    """`BoundingBox` refuse width/height nuls : le recadrage garde au moins 1 px."""
    bbox = clamp_bbox_to_image(300, 200, 300, 200, IMAGE_WIDTH, IMAGE_HEIGHT)

    assert bbox.width >= 1
    assert bbox.height >= 1


def test_box_entirely_outside_the_image_still_yields_a_valid_box() -> None:
    """Aucune entrée du modèle ne doit pouvoir faire lever le value object."""
    bbox = clamp_bbox_to_image(-400, -400, -100, -100, IMAGE_WIDTH, IMAGE_HEIGHT)

    assert bbox.x >= 0
    assert bbox.y >= 0
    assert bbox.width >= 1
    assert bbox.height >= 1


@pytest.mark.parametrize(
    "coords",
    [
        (-1000.0, -1000.0, -999.0, -999.0),
        (0.0, 0.0, 0.0, 0.0),
        (639.9, 479.9, 640.1, 480.1),
        (5000.0, 5000.0, 6000.0, 6000.0),
    ],
)
def test_never_raises_whatever_the_model_returns(coords: tuple[float, ...]) -> None:
    bbox = clamp_bbox_to_image(*coords, IMAGE_WIDTH, IMAGE_HEIGHT)

    assert bbox.x >= 0 and bbox.y >= 0
    assert bbox.width >= 1 and bbox.height >= 1
