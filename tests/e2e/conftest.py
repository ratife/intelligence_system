"""Fixtures e2e : application FastAPI complète avec adapters ML/queue remplacés par des fakes.

Objectif : valider le câblage bout en bout (routers → use cases → ports) sans
dépendre de poids ONNX réels ni d'un vrai Redis/S3 — seule la base Postgres
réelle (via testcontainers) est utilisée, car pgvector fait partie du contrat
testé (agrégation, seuillage).
"""

from __future__ import annotations

from collections.abc import Iterator
from pathlib import Path

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy import create_engine, text
from sqlalchemy.orm import sessionmaker
from testcontainers.postgres import PostgresContainer

from facereco.domain.entities.face import DetectedFace
from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.infrastructure.config.settings import settings
from facereco.infrastructure.db import session as db_session_module
from facereco.infrastructure.storage.s3_object_storage import ObjectStoragePort
from facereco.interface.api.error_handlers import register_error_handlers
from facereco.interface.api.routers.auth import router as auth_router
from facereco.interface.api.routers.indexing import router as indexing_router
from facereco.interface.api.routers.search import router as search_router
from facereco.interface.api.routers.statistics import router as statistics_router
from tests.unit.application.fakes import DeterministicFaceEmbedder, ScriptedFaceDetector

MIGRATIONS_FILE = Path(__file__).resolve().parents[2] / "migrations" / "0001_init.sql"
ACTOR_HEADERS = {"Authorization": f"Bearer {settings.api_bearer_token}", "X-Actor-Id": "e2e-test"}


class InMemoryObjectStorage(ObjectStoragePort):
    def __init__(self) -> None:
        self.images: dict[str, bytes] = {}

    def get_image_bytes(self, storage_uri: str) -> bytes:
        return self.images[storage_uri]

    def build_signed_url(self, storage_uri: str, expires_in_seconds: int = 300) -> str:
        return f"https://signed.example/{storage_uri}"


class AlwaysAllowQuota:
    def check_and_consume(self, actor_id: str) -> bool:
        return True


@pytest.fixture(scope="module")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture()
def test_app(postgres_container, monkeypatch) -> Iterator[FastAPI]:
    url = postgres_container.get_connection_url().replace("psycopg2", "psycopg")
    engine = create_engine(url)
    with engine.begin() as connection:
        connection.execute(text(MIGRATIONS_FILE.read_text()))

    monkeypatch.setattr(db_session_module, "engine", engine)
    monkeypatch.setattr(
        db_session_module, "SessionFactory", sessionmaker(bind=engine, expire_on_commit=False)
    )

    app = FastAPI()
    app.include_router(auth_router)
    app.include_router(search_router)
    app.include_router(indexing_router)
    app.include_router(statistics_router)
    register_error_handlers(app)

    query_image = b"query-image-bytes"
    faces_by_image = {
        query_image: [
            DetectedFace(
                bbox=BoundingBox(x=0, y=0, width=100, height=100),
                detection_score=0.95,
                sharpness=120.0,
                yaw_degrees=0.0,
                landmarks=((30.0, 40.0), (70.0, 40.0), (50.0, 60.0), (35.0, 80.0), (65.0, 80.0)),
            )
        ]
    }
    app.state.face_detector = ScriptedFaceDetector(faces_by_image)
    app.state.face_embedder = DeterministicFaceEmbedder(version="arcface-r100-v1")
    app.state.object_storage = InMemoryObjectStorage()
    app.state.search_quota = AlwaysAllowQuota()

    yield app

    # Le conteneur Postgres est partagé par tout le module et `CREATE TABLE IF
    # NOT EXISTS` ne remet rien à zéro : sans ce nettoyage, les données d'un test
    # fuiteraient dans le suivant. Même stratégie que les tests d'intégration.
    with engine.begin() as connection:
        for table in (
            "search_audit_log",
            "rejected_faces",
            "face_embeddings",
            "event_images",
            "events",
        ):
            connection.execute(text(f"TRUNCATE TABLE {table} CASCADE"))

    engine.dispose()


@pytest.fixture()
def client(test_app: FastAPI) -> Iterator[TestClient]:
    with TestClient(test_app) as test_client:
        yield test_client
