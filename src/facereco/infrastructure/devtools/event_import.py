"""Créer un événement et lui importer/indexer des images — dev/démo uniquement.

Les ports du Domain (`EventRepositoryPort`, `ObjectStoragePort`) n'exposent
volontairement aucune méthode de création : en production, `events`/
`event_images` et le stockage objet sont alimentés par le système
d'événements pré-existant (§2.1), pas par ce service. Ce module contourne
donc les ports pour les deux points d'entrée dev/démo qui doivent créer des
données (CLI `interface/cli/import_folder.py`, routes
`interface/api/routers/admin_events.py`) — ce n'est pas un use case
applicatif, d'où sa place en Infrastructure plutôt qu'en Application.

Idempotent par contenu : une image déjà importée (même `content_hash`,
contrainte d'unicité `event_images.content_hash`) est signalée comme
doublon plutôt que dupliquée.
"""

from __future__ import annotations

import hashlib
import io
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import boto3
from PIL import Image
from sqlalchemy import select

from facereco.application.dto import IndexImageCommand
from facereco.application.use_cases.process_image_message import ProcessImageMessageUseCase
from facereco.domain.entities.event import Event
from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.infrastructure.config.settings import settings
from facereco.infrastructure.db.event_repository_pg import PostgresEventRepository
from facereco.infrastructure.db.face_embedding_repository_pg import (
    PostgresFaceEmbeddingRepository,
)
from facereco.infrastructure.db.models import EventImageModel, EventModel
from facereco.infrastructure.db.session import session_scope
from facereco.infrastructure.system_clock import SystemClock


@dataclass(frozen=True, slots=True)
class ImportedImage:
    """Résultat de l'import d'une image : nouvelle (indexée) ou doublon ignoré."""

    filename: str
    image_id: int
    duplicate: bool
    faces_accepted: int
    faces_rejected: int


def s3_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def ensure_bucket(s3: Any) -> None:
    """Crée le bucket S3/MinIO s'il n'existe pas déjà (setup dev, cf. README)."""
    try:
        s3.head_bucket(Bucket=settings.s3_bucket)
    except Exception:
        s3.create_bucket(Bucket=settings.s3_bucket)


def _image_size(image_bytes: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return img.size
    except Exception:
        return None, None


def _to_event(row: EventModel) -> Event:
    return Event(
        id=row.id, description=row.description, event_date=row.event_date, address=row.address
    )


def list_events() -> list[Event]:
    with session_scope() as session:
        rows = session.scalars(select(EventModel).order_by(EventModel.id.desc())).all()
        return [_to_event(row) for row in rows]


def get_event(event_id: int) -> Event | None:
    with session_scope() as session:
        row = session.get(EventModel, event_id)
        return _to_event(row) if row is not None else None


def create_event(description: str, event_date: date, address: str) -> Event:
    with session_scope() as session:
        row = EventModel(description=description, event_date=event_date, address=address)
        session.add(row)
        session.flush()
        event = _to_event(row)
    return event


def import_and_index_image(
    event_id: int,
    filename: str,
    image_bytes: bytes,
    face_detector: FaceDetectorPort,
    face_embedder: FaceEmbedderPort,
    object_storage: ObjectStoragePort,
) -> ImportedImage:
    """Upload (si nouveau contenu) puis indexe une image pour un événement existant."""
    content_hash = hashlib.sha256(image_bytes).hexdigest()

    with session_scope() as session:
        existing = session.scalar(
            select(EventImageModel).where(EventImageModel.content_hash == content_hash)
        )
        if existing is not None:
            return ImportedImage(
                filename=filename,
                image_id=existing.id,
                duplicate=True,
                faces_accepted=0,
                faces_rejected=0,
            )

        s3 = s3_client()
        ensure_bucket(s3)
        width, height = _image_size(image_bytes)
        suffix = Path(filename).suffix.lower()
        key = f"import/{event_id}/{content_hash}{suffix}"
        s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=image_bytes)

        image = EventImageModel(
            event_id=event_id,
            storage_uri=f"s3://{settings.s3_bucket}/{key}",
            content_hash=content_hash,
            width=width,
            height=height,
            index_status="pending",
        )
        session.add(image)
        session.flush()
        image_id = image.id

    with session_scope() as session:
        use_case = ProcessImageMessageUseCase(
            event_repository=PostgresEventRepository(session),
            object_storage=object_storage,
            face_detector=face_detector,
            face_embedder=face_embedder,
            face_embedding_repository=PostgresFaceEmbeddingRepository(session),
            clock=SystemClock(),
        )
        result = use_case.execute(IndexImageCommand(image_id=image_id))

    return ImportedImage(
        filename=filename,
        image_id=image_id,
        duplicate=False,
        faces_accepted=result.faces_accepted,
        faces_rejected=result.faces_rejected,
    )
