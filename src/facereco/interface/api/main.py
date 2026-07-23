"""Point d'entrée FastAPI — assemble l'application et instancie les adapters lourds une fois.

Les modèles ONNX (détection, embedding) sont coûteux à charger : ils sont créés
au démarrage (lifespan) et partagés par toutes les requêtes, jamais reconstruits
par la couche de dépendances (voir `deps.py`).
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from contextlib import asynccontextmanager

import redis
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from facereco.infrastructure.config.settings import settings
from facereco.infrastructure.messaging.redis_streams_queue import RedisStreamsQueue
from facereco.infrastructure.ml.arcface_embedder import ArcFaceEmbedder
from facereco.infrastructure.ml.insightface_detector import InsightFaceDetector
from facereco.infrastructure.quota.redis_quota import RedisSearchQuota
from facereco.infrastructure.storage.s3_object_storage import S3ObjectStorage
from facereco.interface.api.error_handlers import register_error_handlers
from facereco.interface.api.routers.admin_events import router as admin_events_router
from facereco.interface.api.routers.indexing import router as indexing_router
from facereco.interface.api.routers.search import router as search_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.face_detector = InsightFaceDetector(
        model_pack=settings.insightface_model_pack, providers=settings.onnx_providers
    )
    app.state.face_embedder = ArcFaceEmbedder(
        model_pack=settings.insightface_model_pack,
        providers=settings.onnx_providers,
        version=settings.model_version,
    )
    app.state.object_storage = S3ObjectStorage(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )
    redis_client = redis.Redis.from_url(settings.redis_url, decode_responses=True)
    app.state.redis_client = redis_client
    app.state.message_queue = RedisStreamsQueue(
        client=redis_client,
        stream=settings.indexing_stream,
        consumer_group=settings.indexing_consumer_group,
        dead_letter_stream=settings.indexing_dead_letter_stream,
    )
    app.state.search_quota = RedisSearchQuota(
        client=redis_client, max_per_minute=settings.search_quota_per_actor_per_minute
    )
    yield
    redis_client.close()


def create_app() -> FastAPI:
    app = FastAPI(
        title="Reconnaissance faciale événementielle",
        version="0.1.0",
        lifespan=lifespan,
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(search_router)
    app.include_router(indexing_router)
    app.include_router(admin_events_router)
    register_error_handlers(app)
    return app


app = create_app()
