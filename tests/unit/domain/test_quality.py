from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.domain.value_objects.quality import (
    DEFAULT_QUALITY_THRESHOLDS,
    assess_face_quality,
)


def _bbox(side: int) -> BoundingBox:
    return BoundingBox(x=0, y=0, width=side, height=side)


def test_accepts_face_above_all_thresholds() -> None:
    result = assess_face_quality(
        bbox=_bbox(100),
        detection_score=0.95,
        sharpness=120.0,
        yaw_degrees=10.0,
    )
    assert result.passed
    assert result.rejection_reason is None


def test_rejects_face_too_small() -> None:
    result = assess_face_quality(
        bbox=_bbox(DEFAULT_QUALITY_THRESHOLDS.min_face_side_px - 1),
        detection_score=0.95,
        sharpness=120.0,
        yaw_degrees=10.0,
    )
    assert not result.passed
    assert "taille_visage" in result.rejection_reason


def test_rejects_low_detection_score() -> None:
    result = assess_face_quality(
        bbox=_bbox(100),
        detection_score=DEFAULT_QUALITY_THRESHOLDS.min_detection_score - 0.01,
        sharpness=120.0,
        yaw_degrees=10.0,
    )
    assert not result.passed
    assert "score_detection" in result.rejection_reason


def test_rejects_blurry_face() -> None:
    result = assess_face_quality(
        bbox=_bbox(100),
        detection_score=0.95,
        sharpness=DEFAULT_QUALITY_THRESHOLDS.min_sharpness - 1,
        yaw_degrees=10.0,
    )
    assert not result.passed
    assert "flou" in result.rejection_reason


def test_rejects_extreme_pose() -> None:
    result = assess_face_quality(
        bbox=_bbox(100),
        detection_score=0.95,
        sharpness=120.0,
        yaw_degrees=DEFAULT_QUALITY_THRESHOLDS.max_yaw_degrees + 1,
    )
    assert not result.passed
    assert "pose" in result.rejection_reason


def test_rejection_reason_required_when_not_passed() -> None:
    import pytest

    from facereco.domain.value_objects.quality import QualityAssessment

    with pytest.raises(ValueError):
        QualityAssessment(passed=False, rejection_reason=None)


def test_no_reason_allowed_when_passed() -> None:
    import pytest

    from facereco.domain.value_objects.quality import QualityAssessment

    with pytest.raises(ValueError):
        QualityAssessment(passed=True, rejection_reason="should not be here")
