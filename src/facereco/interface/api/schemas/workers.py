"""Schemas Pydantic de supervision de la file — distincts des value objects du Domain.

Les qualificatifs dérivés (`is_active`, `is_stalled`) sont exposés **calculés** :
ils encodent le seuil d'inactivité et la définition d'une file bloquée, qu'une
interface ne doit pas redevinner ni diverger.
"""

from __future__ import annotations

from pydantic import BaseModel

from facereco.domain.value_objects.indexing_queue import IndexingQueueStatus


class WorkerSchema(BaseModel):
    name: str
    pending_messages: int
    idle_seconds: float
    inactive_seconds: float
    is_active: bool
    is_working: bool


class QueueStatusResponseSchema(BaseModel):
    consumer_group: str
    workers: list[WorkerSchema]
    active_worker_count: int
    undelivered_messages: int
    unacknowledged_messages: int
    dead_letter_messages: int
    backlog: int
    is_stalled: bool


def to_queue_status_response(status: IndexingQueueStatus) -> QueueStatusResponseSchema:
    return QueueStatusResponseSchema(
        consumer_group=status.consumer_group,
        workers=[
            WorkerSchema(
                name=worker.name,
                pending_messages=worker.pending_messages,
                idle_seconds=worker.idle_seconds,
                inactive_seconds=worker.inactive_seconds,
                is_active=worker.is_active,
                is_working=worker.is_working,
            )
            for worker in status.workers
        ],
        active_worker_count=len(status.active_workers),
        undelivered_messages=status.undelivered_messages,
        unacknowledged_messages=status.unacknowledged_messages,
        dead_letter_messages=status.dead_letter_messages,
        backlog=status.backlog,
        is_stalled=status.is_stalled,
    )
