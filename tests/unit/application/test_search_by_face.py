from datetime import date

import pytest

from facereco.application.dto import SearchByFaceCommand
from facereco.application.use_cases.search_by_face import SearchByFaceUseCase
from facereco.domain.entities.event import Event
from facereco.domain.entities.face import DetectedFace
from facereco.domain.exceptions import (
    AmbiguousFaceSelectionError,
    InvalidFaceIndexError,
    NoFaceDetectedError,
    SearchQuotaExceededError,
)
from facereco.domain.ports.vector_search import VectorSearchHit
from facereco.domain.value_objects.bounding_box import BoundingBox

from .fakes import (
    AlwaysAllowQuota,
    AlwaysDenyQuota,
    DeterministicFaceEmbedder,
    FakeAuditLog,
    FakeEventRepository,
    ScriptedFaceDetector,
    ScriptedVectorSearch,
)

QUERY_IMAGE = b"query-jpeg-bytes"
ONE_FACE = [
    DetectedFace(
        bbox=BoundingBox(x=0, y=0, width=100, height=100),
        detection_score=0.91,
        sharpness=100.0,
        yaw_degrees=0.0,
        landmarks=(),
    )
]
TWO_FACES = ONE_FACE + [
    DetectedFace(
        bbox=BoundingBox(x=200, y=0, width=100, height=100),
        detection_score=0.88,
        sharpness=100.0,
        yaw_degrees=0.0,
        landmarks=(),
    )
]

EVENT = Event(
    id=4821,
    title="Séminaire annuel",
    description="",
    event_date=date(2026, 3, 14),
    address="Antananarivo",
)


def _build_use_case(faces, hits, quota=None, threshold=None):
    event_repository = FakeEventRepository(events={EVENT.id: EVENT})
    detector = ScriptedFaceDetector({QUERY_IMAGE: faces})
    embedder = DeterministicFaceEmbedder()
    vector_search = ScriptedVectorSearch(hits=hits)
    audit_log = FakeAuditLog()
    quota = quota or AlwaysAllowQuota()

    use_case = SearchByFaceUseCase(
        face_detector=detector,
        face_embedder=embedder,
        vector_search=vector_search,
        event_repository=event_repository,
        audit_log=audit_log,
        quota=quota,
    )
    return use_case, audit_log


def _hit(event_id: int, similarity: float, image_id: int = 1) -> VectorSearchHit:
    return VectorSearchHit(
        event_id=event_id,
        image_id=image_id,
        storage_uri=f"s3://bucket/{image_id}.jpg",
        bbox=BoundingBox(x=10, y=10, width=64, height=64),
        similarity=similarity,
    )


def test_raises_when_no_face_detected() -> None:
    use_case, _ = _build_use_case(faces=[], hits=[])
    with pytest.raises(NoFaceDetectedError):
        use_case.execute(SearchByFaceCommand(actor_id="alice", query_image_bytes=QUERY_IMAGE))


def test_raises_ambiguous_when_multiple_faces_and_no_index_given() -> None:
    use_case, _ = _build_use_case(faces=TWO_FACES, hits=[])
    with pytest.raises(AmbiguousFaceSelectionError) as exc_info:
        use_case.execute(SearchByFaceCommand(actor_id="alice", query_image_bytes=QUERY_IMAGE))
    assert exc_info.value.faces_detected == 2


def test_raises_invalid_face_index_out_of_bounds() -> None:
    use_case, _ = _build_use_case(faces=ONE_FACE, hits=[])
    with pytest.raises(InvalidFaceIndexError):
        use_case.execute(
            SearchByFaceCommand(actor_id="alice", query_image_bytes=QUERY_IMAGE, face_index=5)
        )


def test_raises_quota_exceeded() -> None:
    use_case, _ = _build_use_case(faces=ONE_FACE, hits=[], quota=AlwaysDenyQuota())
    with pytest.raises(SearchQuotaExceededError):
        use_case.execute(SearchByFaceCommand(actor_id="alice", query_image_bytes=QUERY_IMAGE))


def test_returns_events_above_threshold_with_evidence() -> None:
    use_case, audit_log = _build_use_case(faces=ONE_FACE, hits=[_hit(EVENT.id, 0.71)])

    result = use_case.execute(SearchByFaceCommand(actor_id="alice", query_image_bytes=QUERY_IMAGE))

    assert len(result.matches) == 1
    assert result.matches[0].event.id == EVENT.id
    assert result.matches[0].evidence.similarity == 0.71
    assert result.threshold_used == pytest.approx(0.38)
    assert len(audit_log.records) == 1
    assert audit_log.records[0]["result_count"] == 1


def test_filters_out_hits_below_threshold() -> None:
    use_case, _ = _build_use_case(faces=ONE_FACE, hits=[_hit(EVENT.id, 0.10)])

    result = use_case.execute(SearchByFaceCommand(actor_id="alice", query_image_bytes=QUERY_IMAGE))

    assert result.matches == ()


def test_custom_threshold_overrides_default() -> None:
    use_case, _ = _build_use_case(faces=ONE_FACE, hits=[_hit(EVENT.id, 0.5)])

    result = use_case.execute(
        SearchByFaceCommand(actor_id="alice", query_image_bytes=QUERY_IMAGE, threshold=0.6)
    )

    assert result.matches == ()
    assert result.threshold_used == 0.6


def test_explicit_face_index_selects_correct_face() -> None:
    use_case, _ = _build_use_case(faces=TWO_FACES, hits=[_hit(EVENT.id, 0.71)])

    result = use_case.execute(
        SearchByFaceCommand(actor_id="alice", query_image_bytes=QUERY_IMAGE, face_index=1)
    )

    assert result.query_info.face_used_index == 1
    assert result.query_info.faces_detected == 2
