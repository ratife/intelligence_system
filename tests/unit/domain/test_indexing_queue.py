"""État de la file d'indexation : ce qu'on peut affirmer, et ce qu'on ne peut pas.

Le point sensible est le vocabulaire : Redis ne dit jamais si un worker tourne,
seulement depuis quand il a sondé la file. `is_active` doit donc rester une
mesure de fraîcheur, jamais une affirmation de vie.
"""

import pytest

from facereco.domain.value_objects.indexing_queue import (
    ACTIVE_IDLE_THRESHOLD_SECONDS,
    IndexingQueueStatus,
    WorkerStatus,
)


def worker(**overrides) -> WorkerStatus:
    defaults = dict(name="hote-123", pending_messages=0, idle_seconds=1.0, inactive_seconds=1.0)
    return WorkerStatus(**{**defaults, **overrides})


def queue(**overrides) -> IndexingQueueStatus:
    defaults = dict(
        consumer_group="facereco-workers",
        workers=(),
        undelivered_messages=0,
        unacknowledged_messages=0,
        dead_letter_messages=0,
    )
    return IndexingQueueStatus(**{**defaults, **overrides})


def test_recently_polling_consumer_is_active() -> None:
    assert worker(idle_seconds=ACTIVE_IDLE_THRESHOLD_SECONDS - 1).is_active


def test_silent_consumer_is_not_active() -> None:
    """Une entrée de consommateur survit au processus : le silence prolongé suffit."""
    assert not worker(idle_seconds=ACTIVE_IDLE_THRESHOLD_SECONDS + 1).is_active


def test_long_inactivity_does_not_make_a_polling_consumer_inactive() -> None:
    """Un worker vivant mais sans travail n'a rien à lire : c'est normal."""
    assert worker(idle_seconds=2.0, inactive_seconds=86_400.0).is_active


def test_consumer_holding_a_message_is_working() -> None:
    assert worker(pending_messages=3).is_working
    assert not worker(pending_messages=0).is_working


def test_backlog_sums_undelivered_and_unacknowledged() -> None:
    assert queue(undelivered_messages=7, unacknowledged_messages=3).backlog == 10


def test_queue_is_stalled_when_work_waits_without_an_active_consumer() -> None:
    stalled = queue(undelivered_messages=5, workers=(worker(idle_seconds=600.0),))

    assert stalled.is_stalled


def test_queue_with_an_active_consumer_is_not_stalled() -> None:
    busy = queue(undelivered_messages=5, workers=(worker(idle_seconds=1.0),))

    assert not busy.is_stalled


def test_empty_queue_without_consumers_is_not_stalled() -> None:
    """Pas de travail en attente : l'absence de worker n'est pas un incident."""
    assert not queue(workers=()).is_stalled


def test_active_workers_filters_on_freshness() -> None:
    status = queue(
        workers=(
            worker(name="vivant", idle_seconds=1.0),
            worker(name="perime", idle_seconds=50_000.0),
        )
    )

    assert [w.name for w in status.active_workers] == ["vivant"]


def test_dead_letters_are_flagged() -> None:
    assert queue(dead_letter_messages=53).has_dead_letters
    assert not queue(dead_letter_messages=0).has_dead_letters


def test_consumer_name_cannot_be_empty() -> None:
    with pytest.raises(ValueError, match="nom de consommateur"):
        worker(name="")


def test_negative_counters_are_rejected() -> None:
    with pytest.raises(ValueError, match="pending_messages"):
        worker(pending_messages=-1)
    with pytest.raises(ValueError, match="dead_letter_messages"):
        queue(dead_letter_messages=-2)
