"""Les taux du tableau de bord : dénominateurs, division par zéro, invariants."""

import pytest

from facereco.domain.value_objects.system_statistics import (
    RejectionReasonCount,
    SystemStatistics,
)


def make_statistics(**overrides) -> SystemStatistics:
    defaults = dict(
        event_count=0,
        image_count=0,
        indexed_image_count=0,
        pending_image_count=0,
        face_count=0,
        rejected_face_count=0,
        search_count=0,
        empty_search_count=0,
        distinct_actor_count=0,
        average_top_score=None,
    )
    return SystemStatistics(**{**defaults, **overrides})


def test_empty_system_reports_zero_rates_rather_than_failing() -> None:
    """Un système vide n'est pas une erreur : tous les taux valent 0.0."""
    statistics = make_statistics()

    assert statistics.indexing_completion_rate == 0.0
    assert statistics.quality_rejection_rate == 0.0
    assert statistics.average_faces_per_indexed_image == 0.0
    assert statistics.empty_search_rate == 0.0
    assert statistics.detected_face_count == 0


def test_indexing_completion_rate_is_over_all_images() -> None:
    statistics = make_statistics(image_count=10, indexed_image_count=4, pending_image_count=6)

    assert statistics.indexing_completion_rate == pytest.approx(0.4)


def test_quality_rejection_rate_is_over_detected_faces_not_images() -> None:
    """Le dénominateur est le nombre de visages détectés (retenus + écartés)."""
    statistics = make_statistics(
        image_count=5, indexed_image_count=5, face_count=30, rejected_face_count=10
    )

    assert statistics.detected_face_count == 40
    assert statistics.quality_rejection_rate == pytest.approx(0.25)


def test_faces_per_image_ignores_pending_images() -> None:
    """Les images en attente n'ont produit aucun visage : les compter écraserait la moyenne."""
    statistics = make_statistics(
        image_count=100, indexed_image_count=10, pending_image_count=90, face_count=30
    )

    assert statistics.average_faces_per_indexed_image == pytest.approx(3.0)


def test_empty_search_rate_tracks_threshold_calibration() -> None:
    statistics = make_statistics(search_count=8, empty_search_count=6)

    assert statistics.empty_search_rate == pytest.approx(0.75)


def test_rejections_by_reason_is_carried_verbatim() -> None:
    reasons = (
        RejectionReasonCount(reason="trop_petit", count=7),
        RejectionReasonCount(reason="flou", count=3),
    )
    statistics = make_statistics(rejected_face_count=10, rejections_by_reason=reasons)

    assert statistics.rejections_by_reason == reasons


def test_negative_counter_is_rejected() -> None:
    with pytest.raises(ValueError, match="face_count"):
        make_statistics(face_count=-1)


def test_negative_rejection_reason_count_is_rejected() -> None:
    with pytest.raises(ValueError, match="flou"):
        RejectionReasonCount(reason="flou", count=-2)


def test_indexed_cannot_exceed_total_images() -> None:
    """Invariant de sous-ensemble : le violer signale une requête d'agrégation fausse."""
    with pytest.raises(ValueError, match="indexed_image_count"):
        make_statistics(image_count=3, indexed_image_count=4)


def test_empty_searches_cannot_exceed_total_searches() -> None:
    with pytest.raises(ValueError, match="empty_search_count"):
        make_statistics(search_count=2, empty_search_count=5)
