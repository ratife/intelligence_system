"""Implémentation Redis Streams du port QueueMonitorPort — supervision de la file.

Traduit les commandes d'introspection de Redis (`XINFO GROUPS`,
`XINFO CONSUMERS`, `XLEN`) en une photographie exploitable par l'interface.

Le groupe de consommateurs peut ne pas exister : tant que rien n'a jamais été
publié ni aucun worker démarré, `XINFO` renvoie une erreur. C'est un état normal
d'installation neuve, pas une panne — il est traduit en file vide.
"""

from __future__ import annotations

from typing import Any

import redis

from facereco.domain.ports.queue_monitor import QueueMonitorPort
from facereco.domain.value_objects.indexing_queue import IndexingQueueStatus, WorkerStatus

_MILLISECONDS = 1000.0


class RedisQueueMonitor(QueueMonitorPort):
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

    def collect(self) -> IndexingQueueStatus:
        group = self._find_group()
        if group is None:
            return IndexingQueueStatus(
                consumer_group=self._group,
                workers=(),
                undelivered_messages=0,
                unacknowledged_messages=0,
                dead_letter_messages=self._stream_length(self._dead_letter_stream),
            )

        return IndexingQueueStatus(
            consumer_group=self._group,
            workers=self._collect_workers(),
            # `lag` : entrées publiées que le groupe n'a encore remises à personne.
            # Redis le renvoie à None lorsqu'il ne peut plus le calculer (entrées
            # supprimées du flux) ; on retombe alors sur 0 plutôt que d'inventer.
            undelivered_messages=max(int(group.get("lag") or 0), 0),
            unacknowledged_messages=max(int(group.get("pending") or 0), 0),
            dead_letter_messages=self._stream_length(self._dead_letter_stream),
        )

    def _find_group(self) -> dict[str, Any] | None:
        try:
            groups: list[dict[str, Any]] = self._redis.xinfo_groups(self._stream)
        except redis.ResponseError:
            return None
        return next((g for g in groups if g.get("name") == self._group), None)

    def _collect_workers(self) -> tuple[WorkerStatus, ...]:
        try:
            consumers: list[dict[str, Any]] = self._redis.xinfo_consumers(self._stream, self._group)
        except redis.ResponseError:
            return ()

        workers = [
            WorkerStatus(
                name=str(consumer["name"]),
                pending_messages=max(int(consumer.get("pending") or 0), 0),
                idle_seconds=max(float(consumer.get("idle") or 0) / _MILLISECONDS, 0.0),
                # `inactive` n'existe qu'à partir de Redis 7 ; à défaut, `idle`
                # est la meilleure approximation disponible.
                inactive_seconds=max(
                    float(consumer.get("inactive", consumer.get("idle", 0)) or 0) / _MILLISECONDS,
                    0.0,
                ),
            )
            for consumer in consumers
        ]
        # Les consommateurs qui travaillent d'abord, puis les plus récemment vus.
        workers.sort(key=lambda worker: (-worker.pending_messages, worker.idle_seconds))
        return tuple(workers)

    def _stream_length(self, stream: str) -> int:
        try:
            return int(self._redis.xlen(stream))
        except redis.ResponseError:
            return 0
