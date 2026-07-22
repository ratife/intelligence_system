"""Implémentation Redis Streams du port MessageQueuePort.

Groupe de consommateurs + ACK explicite + dead-letter queue, comme requis par
le document (§6.1, « robustesse opérationnelle »). La politique de retry (3
tentatives) est décidée par l'appelant (worker) à partir de `delivery_count` ;
ce port n'expose que les primitives Redis Streams.
"""

from __future__ import annotations

from typing import cast

import redis

from facereco.domain.ports.message_queue import MessageQueuePort, QueueMessage

XAutoclaimResult = tuple[str, list[tuple[str, dict[str, str]]], list[str]]
XReadGroupResult = list[tuple[str, list[tuple[str, dict[str, str]]]]]

_START_OF_STREAM = "0"

# Plancher de backoff avant qu'un message non-acquitté redevienne éligible à la
# reprise (§6.1 « 3 tentatives avec backoff exponentiel »). Une vraie exponentielle
# par tentative demanderait un flux de retry différé dédié ; ce plancher fixe est
# une simplification volontaire du MVP, à durcir en Lot 3.
_RETRY_MIN_IDLE_MS = 5_000


class RedisStreamsQueue(MessageQueuePort):
    def __init__(
        self,
        client: redis.Redis,
        stream: str,
        consumer_group: str,
        dead_letter_stream: str,
    ) -> None:
        self._redis = client
        self._stream = stream
        self._group = consumer_group
        self._dead_letter_stream = dead_letter_stream
        self._ensure_consumer_group()

    def _ensure_consumer_group(self) -> None:
        try:
            self._redis.xgroup_create(self._stream, self._group, id=_START_OF_STREAM, mkstream=True)
        except redis.ResponseError as exc:
            if "BUSYGROUP" not in str(exc):
                raise

    def publish_image_for_indexing(self, image_id: int) -> None:
        self._redis.xadd(self._stream, {"image_id": str(image_id)})

    def read_pending(self, consumer_name: str, count: int) -> list[QueueMessage]:
        # D'abord réclamer les messages déjà en attente depuis au moins
        # _RETRY_MIN_IDLE_MS (reprise sur erreur), sinon lire de nouveaux messages.
        _cursor, claimed_entries, _deleted = cast(
            XAutoclaimResult,
            self._redis.xautoclaim(
                name=self._stream,
                groupname=self._group,
                consumername=consumer_name,
                min_idle_time=_RETRY_MIN_IDLE_MS,
                start_id="0-0",
                count=count,
            ),
        )
        if claimed_entries:
            return [
                self._to_queue_message(message_id, fields) for message_id, fields in claimed_entries
            ]

        response = cast(
            XReadGroupResult,
            self._redis.xreadgroup(
                groupname=self._group,
                consumername=consumer_name,
                streams={self._stream: ">"},
                count=count,
            ),
        )
        if not response:
            return []

        messages: list[QueueMessage] = []
        for _stream_name, entries in response:
            for message_id, fields in entries:
                messages.append(self._to_queue_message(message_id, fields))
        return messages

    def _to_queue_message(self, message_id: str, fields: dict[str, str]) -> QueueMessage:
        return QueueMessage(
            message_id=message_id,
            image_id=int(fields["image_id"]),
            delivery_count=self._delivery_count(message_id),
        )

    def _delivery_count(self, message_id: str) -> int:
        pending = self._redis.xpending_range(
            self._stream, self._group, min=message_id, max=message_id, count=1
        )
        if not pending:
            return 1
        return int(pending[0]["times_delivered"])

    def acknowledge(self, message: QueueMessage) -> None:
        self._redis.xack(self._stream, self._group, message.message_id)

    def dead_letter(self, message: QueueMessage, reason: str) -> None:
        self._redis.xadd(
            self._dead_letter_stream,
            {
                "image_id": str(message.image_id),
                "reason": reason,
                "original_message_id": message.message_id,
            },
        )
        self._redis.xack(self._stream, self._group, message.message_id)
