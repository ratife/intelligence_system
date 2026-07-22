from facereco.application.dto import TriggerIndexingCommand
from facereco.application.use_cases.index_event_images import TriggerIndexingUseCase
from facereco.domain.entities.event import EventImage, IndexStatus
from facereco.domain.value_objects.model_version import ModelVersion

from .fakes import FakeEventRepository, FakeMessageQueue


def _image(image_id: int, status: IndexStatus) -> EventImage:
    return EventImage(
        id=image_id,
        event_id=1,
        storage_uri=f"s3://bucket/{image_id}.jpg",
        content_hash=str(image_id),
        width=800,
        height=600,
        index_status=status,
    )


def test_publishes_only_images_needing_indexing() -> None:
    event_repository = FakeEventRepository(
        images={
            1: _image(1, IndexStatus.PENDING),
            2: _image(2, IndexStatus.DONE),
            3: _image(3, IndexStatus.FAILED),
        }
    )
    queue = FakeMessageQueue()
    use_case = TriggerIndexingUseCase(
        event_repository=event_repository,
        message_queue=queue,
        current_model_version=ModelVersion(value="arcface-r100-v1"),
    )

    result = use_case.execute(TriggerIndexingCommand(batch_limit=10))

    assert result.images_published == 2
    assert set(queue.published) == {1, 3}


def test_respects_batch_limit() -> None:
    event_repository = FakeEventRepository(
        images={i: _image(i, IndexStatus.PENDING) for i in range(1, 6)}
    )
    queue = FakeMessageQueue()
    use_case = TriggerIndexingUseCase(
        event_repository=event_repository,
        message_queue=queue,
        current_model_version=ModelVersion(value="arcface-r100-v1"),
    )

    result = use_case.execute(TriggerIndexingCommand(batch_limit=2))

    assert result.images_published == 2
    assert len(queue.published) == 2
