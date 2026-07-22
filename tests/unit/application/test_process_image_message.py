from datetime import datetime

from facereco.application.dto import IndexImageCommand
from facereco.application.use_cases.process_image_message import ProcessImageMessageUseCase
from facereco.domain.entities.event import EventImage, IndexStatus
from facereco.domain.entities.face import DetectedFace
from facereco.domain.value_objects.bounding_box import BoundingBox

from .fakes import (
    DeterministicFaceEmbedder,
    FakeEventRepository,
    FakeFaceEmbeddingRepository,
    FakeObjectStorage,
    FixedClock,
    ScriptedFaceDetector,
)

IMAGE_BYTES = b"fake-jpeg-bytes"


def _good_face(seed: int) -> DetectedFace:
    return DetectedFace(
        bbox=BoundingBox(x=seed, y=0, width=100, height=100),
        detection_score=0.95,
        sharpness=120.0,
        yaw_degrees=5.0,
        landmarks=(),
    )


def _tiny_face() -> DetectedFace:
    return DetectedFace(
        bbox=BoundingBox(x=0, y=0, width=20, height=20),
        detection_score=0.95,
        sharpness=120.0,
        yaw_degrees=5.0,
        landmarks=(),
    )


def _build_use_case(faces: list[DetectedFace]):
    event_repository = FakeEventRepository(
        images={
            1: EventImage(
                id=1,
                event_id=42,
                storage_uri="s3://bucket/img1.jpg",
                content_hash="abc",
                width=800,
                height=600,
                index_status=IndexStatus.PENDING,
            )
        }
    )
    storage = FakeObjectStorage()
    storage.images["s3://bucket/img1.jpg"] = IMAGE_BYTES
    detector = ScriptedFaceDetector({IMAGE_BYTES: faces})
    embedder = DeterministicFaceEmbedder()
    embedding_repository = FakeFaceEmbeddingRepository()
    clock = FixedClock(datetime(2026, 7, 21, 10, 0, 0))

    use_case = ProcessImageMessageUseCase(
        event_repository=event_repository,
        object_storage=storage,
        face_detector=detector,
        face_embedder=embedder,
        face_embedding_repository=embedding_repository,
        clock=clock,
    )
    return use_case, event_repository, embedding_repository


def test_accepts_good_quality_faces_and_persists_embeddings() -> None:
    use_case, event_repository, embedding_repository = _build_use_case(
        [_good_face(0), _good_face(1)]
    )

    result = use_case.execute(IndexImageCommand(image_id=1))

    assert result.faces_accepted == 2
    assert result.faces_rejected == 0
    assert len(embedding_repository.saved) == 2
    assert embedding_repository.saved[0].event_id == 42
    assert embedding_repository.saved[0].model_version.value == "fake-embedder-v1"


def test_rejects_low_quality_face_and_records_reason() -> None:
    use_case, _, embedding_repository = _build_use_case([_tiny_face()])

    result = use_case.execute(IndexImageCommand(image_id=1))

    assert result.faces_accepted == 0
    assert result.faces_rejected == 1
    assert len(embedding_repository.saved) == 0
    assert embedding_repository.rejected[0][0] == 1  # image_id
    assert "taille_visage" in embedding_repository.rejected[0][2]


def test_marks_image_as_done_after_processing() -> None:
    use_case, event_repository, _ = _build_use_case([_good_face(0)])

    use_case.execute(IndexImageCommand(image_id=1))

    assert event_repository.status_updates == [(1, IndexStatus.DONE)]
    assert event_repository.images[1].index_status == IndexStatus.DONE
    assert event_repository.images[1].indexed_at == datetime(2026, 7, 21, 10, 0, 0)


def test_face_index_matches_position_in_detection_order() -> None:
    use_case, _, embedding_repository = _build_use_case([_good_face(0), _good_face(1)])

    use_case.execute(IndexImageCommand(image_id=1))

    assert [e.face_index for e in embedding_repository.saved] == [0, 1]
