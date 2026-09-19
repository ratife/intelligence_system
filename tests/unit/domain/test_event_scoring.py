import math
from datetime import date

from facereco.domain.entities.event import Event
from facereco.domain.entities.search import FaceCandidate, FaceEvidence
from facereco.domain.services.event_scoring import (
    DEFAULT_CORROBORATION_LAMBDA,
    aggregate_matches_by_event,
)
from facereco.domain.value_objects.bounding_box import BoundingBox

EVENT_A = Event(
    id=1,
    title="Séminaire annuel",
    description="",
    event_date=date(2026, 3, 14),
    address="Antananarivo",
)
EVENT_B = Event(
    id=2,
    title="Conférence",
    description="",
    event_date=date(2026, 4, 1),
    address="Fianarantsoa",
)


def _candidate(event: Event, similarity: float, image_id: int = 1) -> FaceCandidate:
    return FaceCandidate(
        event=event,
        similarity=similarity,
        evidence=FaceEvidence(
            image_id=image_id,
            storage_uri=f"s3://bucket/{image_id}.jpg",
            bbox=BoundingBox(x=0, y=0, width=80, height=80),
            similarity=similarity,
        ),
    )


def test_single_candidate_score_equals_similarity_plus_corroboration_bonus() -> None:
    matches = aggregate_matches_by_event([_candidate(EVENT_A, 0.71)])
    assert len(matches) == 1
    expected = 0.71 + DEFAULT_CORROBORATION_LAMBDA * math.log(1 + 1)
    assert math.isclose(matches[0].confidence, expected, abs_tol=1e-9)
    assert matches[0].match_count == 1


def test_multiple_matches_use_best_similarity_and_corroboration_count() -> None:
    candidates = [
        _candidate(EVENT_A, 0.60, image_id=1),
        _candidate(EVENT_A, 0.75, image_id=2),
        _candidate(EVENT_A, 0.55, image_id=3),
    ]
    matches = aggregate_matches_by_event(candidates)
    assert len(matches) == 1
    match = matches[0]
    assert match.match_count == 3
    assert match.evidence.similarity == 0.75
    expected = 0.75 + DEFAULT_CORROBORATION_LAMBDA * math.log(1 + 3)
    assert math.isclose(match.confidence, expected, abs_tol=1e-9)


def test_results_sorted_by_confidence_descending() -> None:
    candidates = [_candidate(EVENT_A, 0.40), _candidate(EVENT_B, 0.90)]
    matches = aggregate_matches_by_event(candidates)
    assert [m.event.id for m in matches] == [EVENT_B.id, EVENT_A.id]


def test_events_grouped_independently() -> None:
    candidates = [
        _candidate(EVENT_A, 0.5, image_id=1),
        _candidate(EVENT_A, 0.6, image_id=2),
        _candidate(EVENT_B, 0.9, image_id=3),
    ]
    matches = aggregate_matches_by_event(candidates)
    by_event = {m.event.id: m for m in matches}
    assert by_event[EVENT_A.id].match_count == 2
    assert by_event[EVENT_B.id].match_count == 1


def test_corroboration_never_lets_weaker_event_beat_a_much_stronger_single_match() -> None:
    # Un événement avec 50 correspondances moyennes ne doit pas éclipser
    # un événement avec un match quasi parfait mais isolé — le bonus est borné
    # par le log, pas linéaire.
    many_weak = [_candidate(EVENT_A, 0.39, image_id=i) for i in range(50)]
    one_strong = [_candidate(EVENT_B, 0.95, image_id=100)]
    matches = aggregate_matches_by_event(many_weak + one_strong)
    assert matches[0].event.id == EVENT_B.id
