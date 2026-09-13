"""Use case de supervision : restituer l'état de la file d'indexation.

Lecture seule, comme `get_system_statistics` : l'orchestration est minimale mais
le use case existe pour que l'Interface ne dépende jamais d'un adapter concret.
"""

from __future__ import annotations

from facereco.domain.ports.queue_monitor import QueueMonitorPort
from facereco.domain.value_objects.indexing_queue import IndexingQueueStatus


class GetIndexingQueueStatusUseCase:
    def __init__(self, queue_monitor: QueueMonitorPort) -> None:
        self._queue_monitor = queue_monitor

    def execute(self) -> IndexingQueueStatus:
        return self._queue_monitor.collect()
