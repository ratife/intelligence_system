import pytest

from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.domain.value_objects.model_version import ModelVersion
from facereco.domain.value_objects.similarity import SimilarityScore


def test_bounding_box_side_is_min_of_width_height() -> None:
    assert BoundingBox(x=0, y=0, width=80, height=60).side == 60


def test_bounding_box_rejects_non_positive_dimensions() -> None:
    with pytest.raises(ValueError):
        BoundingBox(x=0, y=0, width=0, height=10)


def test_bounding_box_rejects_negative_origin() -> None:
    with pytest.raises(ValueError):
        BoundingBox(x=-1, y=0, width=10, height=10)


def test_model_version_rejects_empty_string() -> None:
    with pytest.raises(ValueError):
        ModelVersion(value="  ")


def test_model_version_str() -> None:
    assert str(ModelVersion(value="arcface-r100-v1")) == "arcface-r100-v1"


def test_similarity_score_bounds() -> None:
    with pytest.raises(ValueError):
        SimilarityScore(value=1.5)
    with pytest.raises(ValueError):
        SimilarityScore(value=-1.5)


def test_similarity_score_meets_threshold() -> None:
    assert SimilarityScore(value=0.5).meets_threshold(0.38)
    assert not SimilarityScore(value=0.2).meets_threshold(0.38)
