"""Outil dev : importe un dossier local d'images dans le système et les indexe réellement.

Contrairement à `index_folder` (détection/qualité/embedding en mémoire, sans
aucune écriture), cet outil effectue l'indexation complète (§6, figure 2) :
il crée les lignes `events`/`event_images`, upload les fichiers dans le
stockage objet (MinIO/S3), puis exécute `ProcessImageMessageUseCase` comme le
ferait le worker de production — les empreintes sont persistées et
deviennent réellement cherchables via `/api/v1/search/by-face`.

Écrit directement en base et dans le stockage objet en amont de
l'indexation, en contournant volontairement les ports du Domain : ceux-ci
n'exposent aucune méthode de création (`EventRepositoryPort`,
`ObjectStoragePort`) car en production `events`/`event_images` et le
stockage objet sont alimentés par le système d'événements pré-existant
(§2.1) — ce script est un amorçage dev/démo, pas un use case applicatif.

Idempotent par contenu : une image déjà importée (même `content_hash`) est
ignorée plutôt que dupliquée (même contrainte d'unicité qu'en production).

Usage :
    python -m facereco.interface.cli.import_folder /chemin/vers/dossier
    python -m facereco.interface.cli.import_folder /chemin --event-id 1
"""

from __future__ import annotations

import argparse
import hashlib
import io
import logging
from datetime import date
from pathlib import Path
from typing import Any

import boto3
from PIL import Image
from sqlalchemy import select
from sqlalchemy.orm import Session

from facereco.application.dto import IndexImageCommand
from facereco.application.use_cases.process_image_message import ProcessImageMessageUseCase
from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.infrastructure.config.settings import settings
from facereco.infrastructure.db.event_repository_pg import PostgresEventRepository
from facereco.infrastructure.db.face_embedding_repository_pg import (
    PostgresFaceEmbeddingRepository,
)
from facereco.infrastructure.db.models import EventImageModel, EventModel
from facereco.infrastructure.db.session import session_scope
from facereco.infrastructure.ml.arcface_embedder import ArcFaceEmbedder
from facereco.infrastructure.ml.insightface_detector import InsightFaceDetector
from facereco.infrastructure.storage.s3_object_storage import S3ObjectStorage
from facereco.infrastructure.system_clock import SystemClock
from facereco.interface.cli.index_folder import iter_image_paths

logger = logging.getLogger("facereco.cli.import_folder")


def _s3_client() -> Any:
    return boto3.client(
        "s3",
        endpoint_url=settings.s3_endpoint_url,
        aws_access_key_id=settings.s3_access_key,
        aws_secret_access_key=settings.s3_secret_key,
        region_name=settings.s3_region,
    )


def _image_size(image_bytes: bytes) -> tuple[int | None, int | None]:
    try:
        with Image.open(io.BytesIO(image_bytes)) as img:
            return img.size
    except Exception:
        return None, None


def _resolve_event_id(session: Session, args: argparse.Namespace, folder: Path) -> int:
    if args.event_id is not None:
        event = session.get(EventModel, args.event_id)
        if event is None:
            raise SystemExit(f"Événement {args.event_id} introuvable.")
        return int(args.event_id)

    event = EventModel(
        description=args.description or f"Import local — {folder.name}",
        event_date=date.fromisoformat(args.event_date) if args.event_date else date.today(),
        address=args.address or "Import CLI (dev)",
    )
    session.add(event)
    session.flush()
    logger.info("événement créé : id=%s (%s)", event.id, event.description)
    return event.id


def _bootstrap_images(folder: Path, event_id: int) -> list[int]:
    image_paths = iter_image_paths(folder)
    if not image_paths:
        logger.warning("aucune image trouvée dans %s", folder)
        return []

    s3 = _s3_client()
    created_image_ids: list[int] = []

    with session_scope() as session:
        for path in image_paths:
            image_bytes = path.read_bytes()
            content_hash = hashlib.sha256(image_bytes).hexdigest()

            existing = session.scalar(
                select(EventImageModel).where(EventImageModel.content_hash == content_hash)
            )
            if existing is not None:
                logger.info("%s : déjà importé (image_id=%s), ignoré", path.name, existing.id)
                continue

            width, height = _image_size(image_bytes)
            key = f"import/{event_id}/{content_hash}{path.suffix.lower()}"
            s3.put_object(Bucket=settings.s3_bucket, Key=key, Body=image_bytes)
            storage_uri = f"s3://{settings.s3_bucket}/{key}"

            image = EventImageModel(
                event_id=event_id,
                storage_uri=storage_uri,
                content_hash=content_hash,
                width=width,
                height=height,
                index_status="pending",
            )
            session.add(image)
            session.flush()
            created_image_ids.append(image.id)
            logger.info("%s : importé (image_id=%s, %s)", path.name, image.id, storage_uri)

    return created_image_ids


def _index_images(image_ids: list[int]) -> None:
    if not image_ids:
        return

    face_detector: FaceDetectorPort = InsightFaceDetector(
        model_pack=settings.insightface_model_pack, providers=settings.onnx_providers
    )
    face_embedder: FaceEmbedderPort = ArcFaceEmbedder(
        model_pack=settings.insightface_model_pack,
        providers=settings.onnx_providers,
        version=settings.model_version,
    )
    object_storage = S3ObjectStorage(
        endpoint_url=settings.s3_endpoint_url,
        access_key=settings.s3_access_key,
        secret_key=settings.s3_secret_key,
        region=settings.s3_region,
    )

    for image_id in image_ids:
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
            logger.info(
                "image %s indexée : %s visage(s) accepté(s), %s rejeté(s)",
                result.image_id,
                result.faces_accepted,
                result.faces_rejected,
            )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Importe un dossier local d'images dans le système (création "
            "events/event_images + upload S3/MinIO) et les indexe réellement "
            "(détection → qualité → embedding → persistance), comme le "
            "ferait le worker de production."
        )
    )
    parser.add_argument("folder", type=Path, help="Dossier contenant les images à importer.")
    parser.add_argument(
        "--event-id",
        type=int,
        default=None,
        help="ID d'un événement existant auquel rattacher les images "
        "(sinon un nouvel événement est créé).",
    )
    parser.add_argument(
        "--description", default=None, help="Description du nouvel événement (si créé)."
    )
    parser.add_argument(
        "--event-date",
        default=None,
        help="Date AAAA-MM-JJ du nouvel événement (défaut : aujourd'hui).",
    )
    parser.add_argument("--address", default=None, help="Adresse du nouvel événement (si créé).")
    args = parser.parse_args()

    if not args.folder.is_dir():
        parser.error(f"{args.folder} n'est pas un dossier.")

    logging.basicConfig(level=logging.INFO, format="%(message)s")

    with session_scope() as session:
        event_id = _resolve_event_id(session, args, args.folder)

    image_ids = _bootstrap_images(args.folder, event_id)
    _index_images(image_ids)

    logger.info(
        "terminé : événement %s, %s image(s) importée(s) et indexée(s)",
        event_id,
        len(image_ids),
    )


if __name__ == "__main__":
    main()
