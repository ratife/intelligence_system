"""Fixtures d'intégration : Postgres+pgvector et Redis via testcontainers.

Ces tests valident les adapters Infrastructure réels (§ ordre d'implémentation,
étape 3) et sont marqués `integration` — ils nécessitent Docker et ne tournent
pas dans la boucle rapide `pytest tests/unit`.
"""

from __future__ import annotations

from collections.abc import Iterator

import pytest
import redis as redis_lib
from sqlalchemy import create_engine, text
from sqlalchemy.orm import Session, sessionmaker
from testcontainers.postgres import PostgresContainer
from testcontainers.redis import RedisContainer

from tests.db_schema import apply_migrations


@pytest.fixture(scope="module")
def postgres_container() -> Iterator[PostgresContainer]:
    with PostgresContainer("pgvector/pgvector:pg16") as container:
        yield container


@pytest.fixture(scope="module")
def db_engine(postgres_container: PostgresContainer):
    url = postgres_container.get_connection_url().replace("psycopg2", "psycopg")
    engine = create_engine(url)
    apply_migrations(engine)
    yield engine
    engine.dispose()


@pytest.fixture()
def db_session(db_engine) -> Iterator[Session]:
    session_factory = sessionmaker(bind=db_engine, expire_on_commit=False)
    session = session_factory()
    try:
        yield session
        session.rollback()
    finally:
        for table in (
            "search_audit_log",
            "rejected_faces",
            "face_embeddings",
            "event_images",
            "events",
        ):
            session.execute(text(f"TRUNCATE TABLE {table} CASCADE"))
        session.commit()
        session.close()


@pytest.fixture(scope="module")
def redis_container() -> Iterator[RedisContainer]:
    with RedisContainer("redis:7-alpine") as container:
        yield container


@pytest.fixture()
def redis_client(redis_container: RedisContainer) -> Iterator[redis_lib.Redis]:
    client = redis_lib.Redis(
        host=redis_container.get_container_host_ip(),
        port=int(redis_container.get_exposed_port(6379)),
        decode_responses=True,
    )
    yield client
    client.flushall()
    client.close()
