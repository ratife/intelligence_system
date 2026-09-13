"""Port de lecture de l'état de la file d'indexation (supervision).

Port de *lecture*, distinct de `MessageQueuePort` : celui-ci publie, lit et
acquitte des messages — le pipeline en dépend. Celui-là ne fait qu'observer, pour
l'interface de supervision. Les mélanger obligerait le pipeline à porter des
méthodes d'introspection dont il n'a aucun usage.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from facereco.domain.value_objects.indexing_queue import IndexingQueueStatus


class QueueMonitorPort(ABC):
    @abstractmethod
    def collect(self) -> IndexingQueueStatus:
        """Photographie de la file : consommateurs, retard, rebuts."""
        raise NotImplementedError
