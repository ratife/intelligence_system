import pytest

from facereco.infrastructure.messaging.redis_streams_queue import RedisStreamsQueue

pytestmark = pytest.mark.integration

STREAM = "test:indexing"
GROUP = "test-workers"
DLQ = "test:indexing:dlq"


def _queue(redis_client) -> RedisStreamsQueue:
    return RedisStreamsQueue(
        client=redis_client, stream=STREAM, consumer_group=GROUP, dead_letter_stream=DLQ
    )


def test_publish_then_read_returns_message(redis_client) -> None:
    queue = _queue(redis_client)
    queue.publish_image_for_indexing(42)

    messages = queue.read_pending("consumer-1", count=10)

    assert len(messages) == 1
    assert messages[0].image_id == 42
    assert messages[0].delivery_count == 1


def test_acknowledge_removes_from_pending(redis_client) -> None:
    queue = _queue(redis_client)
    queue.publish_image_for_indexing(1)
    [message] = queue.read_pending("consumer-1", count=10)

    queue.acknowledge(message)

    assert queue.read_pending("consumer-1", count=10) == []


def test_dead_letter_publishes_to_dlq_and_acks_original(redis_client) -> None:
    queue = _queue(redis_client)
    queue.publish_image_for_indexing(7)
    [message] = queue.read_pending("consumer-1", count=10)

    queue.dead_letter(message, reason="image corrompue")

    dlq_entries = redis_client.xrange(DLQ)
    assert len(dlq_entries) == 1
    _id, fields = dlq_entries[0]
    assert fields["image_id"] == "7"
    assert fields["reason"] == "image corrompue"
    assert queue.read_pending("consumer-1", count=10) == []
