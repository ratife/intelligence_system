"""Port de file de messages pour le découplage indexation écriture/lecture (P1).

Modélise les garanties requises par le document (§6.1 « robustesse
opérationnelle ») : groupes de consommateurs, ACK explicite, dead-letter queue —
sans imposer Redis Streams ou RabbitMQ au domaine.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class QueueMessage:
    """Un message en attente de traitement, avec son compteur de tentatives."""

    message_id: str
    image_id: int
    delivery_count: int


class MessageQueuePort(ABC):
    @abstractmethod
    def publish_image_for_indexing(self, image_id: int) -> None:
        raise NotImplementedError

    @abstractmethod
    def read_pending(self, consumer_name: str, count: int) -> list[QueueMessage]:
        raise NotImplementedError

    @abstractmethod
    def acknowledge(self, message: QueueMessage) -> None:
        raise NotImplementedError

    @abstractmethod
    def dead_letter(self, message: QueueMessage, reason: str) -> None:
        """Bascule en DLQ après épuisement des tentatives — une image corrompue

        ne doit jamais bloquer indéfiniment le traitement du lot (§6.1).
        """
        raise NotImplementedError
