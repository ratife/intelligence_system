"""Worker d'indexation — consomme la file Redis Streams et traite les images (§5, §6.1).

Boucle infinie : lit des messages en attente, exécute le use case, acquitte en
cas de succès, bascule en DLQ après épuisement des tentatives. Une image
corrompue ne doit jamais bloquer indéfiniment le traitement du lot.
"""

from __future__ import annotations

import logging
import os
import socket
import time

import redis

from facereco.application.dto import IndexImageCommand
from facereco.application.use_cases.process_image_message import ProcessImageMessageUseCase
from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.domain.ports.message_queue import QueueMessage
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.infrastructure.config.settings import settings
from facereco.infrastructure.db.event_repository_pg import PostgresEventRepository
from facereco.infrastructure.db.face_embedding_repository_pg import (
    PostgresFaceEmbeddingRepository,
)
from facereco.infrastructure.db.session import session_scope
from facereco.infrastructure.messaging.redis_streams_queue import RedisStreamsQueue
from facereco.infrastructure.ml.arcface_embedder import ArcFaceEmbedder
from facereco.infrastructure.ml.insightface_detector import InsightFaceDetector
from facereco.infrastructure.storage.s3_object_storage import S3ObjectStorage
from facereco.infrastructure.system_clock import SystemClock

logger = logging.getLogger("facereco.worker")

POLL_BATCH_SIZE = 16
POLL_INTERVAL_SECONDS = 2.0


def _process_one(
    message: QueueMessage,
    face_detector: FaceDetectorPort,
    face_embedder: FaceEmbedderPort,
    object_storage: ObjectStoragePort,
) -> None:
    with session_scope() as session:
        use_case = ProcessImageMessageUseCase(
            event_repository=PostgresEventRepository(session),
            object_storage=object_storage,
            face_detector=face_detector,
            face_embedder=face_embedder,
            face_embedding_repository=PostgresFaceEmbeddingRepository(session),
            clock=SystemClock(),
        )
        result = use_case.execute(IndexImageCommand(image_id=message.image_id))
        logger.info(
            "image %s indexée : %s visages acceptés, %s rejetés",
            result.image_id,
            result.faces_accepted,
            result.faces_rejected,
        )


def default_consumer_name() -> str:
    """Nom unique par processus : `<hôte>-<pid>`.

    Redis Streams identifie un consommateur par son nom. Deux processus portant
    le même nom sont vus comme un seul : indiscernables dans la supervision, et
    surtout ils se réclament mutuellement leurs messages en cours via
    `XAUTOCLAIM`, ce qui fait retraiter des images déjà prises en charge.
    """
    return f"{socket.gethostname()}-{os.getpid()}"


def run_worker(consumer_name: str | None = None) -> None:
    consumer_name = consumer_name or default_consumer_name()
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    queue = RedisStreamsQueue(
        client=redis_client,
        stream=settings.indexing_stream,
        consumer_group=settings.indexing_consumer_group,
        dead_letter_stream=settings.indexing_dead_letter_stream,
    )
    face_detector = InsightFaceDetector(
        model_pack=settings.insightface_model_pack, providers=settings.onnx_providers
    )
    face_embedder = ArcFaceEmbedder(
        model_pack=settings.insightface_model_pack,
        providers=settings.onnx_providers,
        version=settings.model_version,
    )
    object_storage = S3ObjectStorage(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
        public_endpoint_url=settings.s3_public_endpoint_url,
    )

    logger.info("worker d'indexation démarré (consumer=%s)", consumer_name)
    while True:
        messages = queue.read_pending(consumer_name, POLL_BATCH_SIZE)
        if not messages:
            time.sleep(POLL_INTERVAL_SECONDS)
            continue

        for message in messages:
            try:
                _process_one(message, face_detector, face_embedder, object_storage)
                queue.acknowledge(message)
            except Exception as exc:  # noqa: BLE001 — une image corrompue ne doit jamais arrêter le worker
                logger.exception("échec de traitement du message %s", message.message_id)
                if message.delivery_count >= settings.indexing_max_delivery_attempts:
                    queue.dead_letter(message, reason=str(exc))
                    logger.warning(
                        "message %s basculé en DLQ après %s tentatives",
                        message.message_id,
                        message.delivery_count,
                    )


if __name__ == "__main__":
    logging.basicConfig(level=logging.INFO)
    run_worker()
