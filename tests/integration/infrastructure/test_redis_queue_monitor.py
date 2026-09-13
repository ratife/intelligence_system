"""Supervision de la file contre un vrai Redis Streams.

Ce que l'adapter doit traduire correctement : le retard du groupe, les messages
remis mais non acquittés, les consommateurs enregistrés, et les rebuts. Les
valeurs viennent de commandes `XINFO` dont la forme varie selon la version de
Redis — d'où un test contre un serveur réel plutôt que des doubles.
"""

from __future__ import annotations

import pytest
import redis as redis_lib

from facereco.infrastructure.messaging.redis_queue_monitor import RedisQueueMonitor
from facereco.infrastructure.messaging.redis_streams_queue import RedisStreamsQueue

pytestmark = pytest.mark.integration

STREAM = "test:indexation"
GROUP = "test-workers"
DLQ = "test:indexation:dlq"


@pytest.fixture()
def queue(redis_client: redis_lib.Redis) -> RedisStreamsQueue:
    for key in (STREAM, DLQ):
        redis_client.delete(key)
    return RedisStreamsQueue(
        client=redis_client, stream=STREAM, consumer_group=GROUP, dead_letter_stream=DLQ
    )


@pytest.fixture()
def monitor(redis_client: redis_lib.Redis) -> RedisQueueMonitor:
    return RedisQueueMonitor(
        client=redis_client, stream=STREAM, consumer_group=GROUP, dead_letter_stream=DLQ
    )


def test_missing_stream_reads_as_an_empty_queue(redis_client: redis_lib.Redis) -> None:
    """Installation neuve : aucun flux, aucun groupe. Ce n'est pas une panne."""
    monitor = RedisQueueMonitor(
        client=redis_client,
        stream="flux:jamais:cree",
        consumer_group="groupe:absent",
        dead_letter_stream="dlq:absente",
    )

    status = monitor.collect()

    assert status.workers == ()
    assert status.backlog == 0
    assert status.dead_letter_messages == 0
    assert not status.is_stalled


def test_published_messages_count_as_undelivered(queue, monitor) -> None:
    queue.publish_image_for_indexing(1)
    queue.publish_image_for_indexing(2)

    status = monitor.collect()

    assert status.undelivered_messages == 2
    assert status.unacknowledged_messages == 0
    assert status.backlog == 2
    # Rien n'a encore lu la file : personne pour prendre le travail.
    assert status.is_stalled


def test_reading_registers_a_consumer_and_moves_work_to_unacknowledged(queue, monitor) -> None:
    queue.publish_image_for_indexing(1)
    queue.publish_image_for_indexing(2)
    queue.read_pending("worker-a", count=10)

    status = monitor.collect()

    assert [worker.name for worker in status.workers] == ["worker-a"]
    assert status.workers[0].pending_messages == 2
    assert status.workers[0].is_working
    assert status.workers[0].is_active
    assert status.undelivered_messages == 0
    assert status.unacknowledged_messages == 2
    assert status.backlog == 2
    # Un consommateur actif détient le travail : la file avance.
    assert not status.is_stalled


def test_acknowledging_empties_the_backlog(queue, monitor) -> None:
    queue.publish_image_for_indexing(1)
    messages = queue.read_pending("worker-a", count=10)
    for message in messages:
        queue.acknowledge(message)

    status = monitor.collect()

    assert status.backlog == 0
    assert status.workers[0].pending_messages == 0
    assert not status.workers[0].is_working


def test_distinct_consumer_names_are_reported_separately(queue, monitor) -> None:
    """Le worker dérive un nom unique par processus : deux workers, deux lignes."""
    queue.publish_image_for_indexing(1)
    queue.publish_image_for_indexing(2)
    queue.read_pending("worker-a", count=1)
    queue.read_pending("worker-b", count=1)

    status = monitor.collect()

    assert sorted(worker.name for worker in status.workers) == ["worker-a", "worker-b"]
    assert sum(worker.pending_messages for worker in status.workers) == 2


def test_dead_letters_are_counted(queue, monitor) -> None:
    queue.publish_image_for_indexing(1)
    messages = queue.read_pending("worker-a", count=10)
    queue.dead_letter(messages[0], reason="image illisible")

    status = monitor.collect()

    assert status.dead_letter_messages == 1
    assert status.has_dead_letters
