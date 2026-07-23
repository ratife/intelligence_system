"""Outil dev : importe un dossier local d'images dans le système et les indexe réellement.

Contrairement à `index_folder` (détection/qualité/embedding en mémoire, sans
aucune écriture), cet outil effectue l'indexation complète (§6, figure 2) via
`infrastructure.devtools.event_import` : création des lignes
`events`/`event_images`, upload dans le stockage objet (MinIO/S3), puis
exécution de `ProcessImageMessageUseCase` comme le ferait le worker de
production — les empreintes sont persistées et deviennent réellement
cherchables via `/api/v1/search/by-face` (ou l'interface web, cf. routes
`/api/v1/admin/events`).

Idempotent par contenu : une image déjà importée (même `content_hash`) est
ignorée plutôt que dupliquée (même contrainte d'unicité qu'en production).

Un sous-dossier = un événement : si le dossier donné contient des
sous-dossiers, chacun est importé comme un événement distinct, dont la
description/date/adresse sont dérivées du *nom du sous-dossier* selon la
convention "<description> - <AAAA-MM-JJ> - <adresse>" (segments manquants ou
mal formés → valeurs par défaut, un nom libre reste un import valide). Les
options --description/--event-date/--address, si fournies, s'appliquent en
override à tous les sous-dossiers. Sans sous-dossier, le dossier donné est
importé comme un seul événement (comportement inchangé).

Usage :
    python -m facereco.interface.cli.import_folder /chemin/vers/dossier
    # 1 sous-dossier = 1 événement :
    python -m facereco.interface.cli.import_folder /chemin/vers/dossier_parent
    python -m facereco.interface.cli.import_folder /chemin --event-id 1
"""

from __future__ import annotations

import argparse
import contextlib
import logging
from datetime import date
from pathlib import Path

from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.domain.ports.object_storage import ObjectStoragePort
from facereco.infrastructure.config.settings import settings
from facereco.infrastructure.devtools.event_import import (
    create_event,
    get_event,
    import_and_index_image,
)
from facereco.infrastructure.ml.arcface_embedder import ArcFaceEmbedder
from facereco.infrastructure.ml.insightface_detector import InsightFaceDetector
from facereco.infrastructure.storage.s3_object_storage import S3ObjectStorage
from facereco.interface.cli.index_folder import iter_image_paths

logger = logging.getLogger("facereco.cli.import_folder")

FOLDER_NAME_SEPARATOR = " - "
DEFAULT_ADDRESS = "Import CLI (dev)"


def _parse_event_metadata(name: str) -> tuple[str, date, str]:
    """Dérive description/date/adresse du nom d'un (sous-)dossier.

    Convention : "<description> - <AAAA-MM-JJ> - <adresse>". Un segment
    manquant ou mal formé retombe sur une valeur par défaut plutôt que
    d'échouer — un nom de dossier libre reste un import valide.
    """
    parts = [part.strip() for part in name.split(FOLDER_NAME_SEPARATOR)]
    description = parts[0] or name

    event_date = date.today()
    if len(parts) >= 2 and parts[1]:
        with contextlib.suppress(ValueError):
            event_date = date.fromisoformat(parts[1])

    address = parts[2] if len(parts) >= 3 and parts[2] else DEFAULT_ADDRESS
    return description, event_date, address


def _import_folder_for_event(
    folder: Path,
    event_id: int,
    face_detector: FaceDetectorPort,
    face_embedder: FaceEmbedderPort,
    object_storage: ObjectStoragePort,
) -> int:
    image_paths = iter_image_paths(folder)
    if not image_paths:
        logger.warning("aucune image trouvée dans %s", folder)
        return 0

    imported = 0
    for path in image_paths:
        result = import_and_index_image(
            event_id, path.name, path.read_bytes(), face_detector, face_embedder, object_storage
        )
        if result.duplicate:
            logger.info("%s : déjà importé (image_id=%s), ignoré", path.name, result.image_id)
            continue
        logger.info(
            "%s : importé et indexé (image_id=%s) — %s visage(s) accepté(s), %s rejeté(s)",
            path.name,
            result.image_id,
            result.faces_accepted,
            result.faces_rejected,
        )
        imported += 1

    return imported


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Importe un dossier local d'images dans le système (création "
            "events/event_images + upload S3/MinIO) et les indexe réellement "
            "(détection → qualité → embedding → persistance), comme le "
            "ferait le worker de production. Si le dossier contient des "
            "sous-dossiers, chacun est importé comme un événement distinct "
            "dont la description/date/adresse sont dérivées du nom du "
            "sous-dossier (convention '<description> - <AAAA-MM-JJ> - <adresse>')."
        )
    )
    parser.add_argument("folder", type=Path, help="Dossier contenant les images à importer.")
    parser.add_argument(
        "--event-id",
        type=int,
        default=None,
        help="ID d'un événement existant auquel rattacher les images de ce dossier "
        "(désactive le mode sous-dossiers).",
    )
    parser.add_argument(
        "--description",
        default=None,
        help="Description à utiliser (override le nom déduit du dossier/sous-dossier).",
    )
    parser.add_argument(
        "--event-date",
        default=None,
        help="Date AAAA-MM-JJ à utiliser (override le nom déduit du dossier/sous-dossier).",
    )
    parser.add_argument(
        "--address",
        default=None,
        help="Adresse à utiliser (override le nom déduit du dossier/sous-dossier).",
    )
    args = parser.parse_args()

    if not args.folder.is_dir():
        parser.error(f"{args.folder} n'est pas un dossier.")

    logging.basicConfig(level=logging.INFO, format="%(message)s")

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
    )

    if args.event_id is not None:
        if get_event(args.event_id) is None:
            raise SystemExit(f"Événement {args.event_id} introuvable.")
        total = _import_folder_for_event(
            args.folder, args.event_id, face_detector, face_embedder, object_storage
        )
        logger.info(
            "terminé : événement %s, %s image(s) importée(s) et indexée(s)",
            args.event_id,
            total,
        )
        return

    subdirs = sorted(p for p in args.folder.iterdir() if p.is_dir() and not p.name.startswith("."))

    if not subdirs:
        description = args.description or f"Import local — {args.folder.name}"
        event_date = date.fromisoformat(args.event_date) if args.event_date else date.today()
        address = args.address or DEFAULT_ADDRESS
        event = create_event(description, event_date, address)
        logger.info("événement créé : id=%s (%s)", event.id, event.description)
        total = _import_folder_for_event(
            args.folder, event.id, face_detector, face_embedder, object_storage
        )
        logger.info("terminé : 1 événement, %s image(s) importée(s) et indexée(s)", total)
        return

    loose_images = iter_image_paths(args.folder)
    if loose_images:
        logger.warning(
            "%s image(s) directement dans %s ignorée(s) — déplacez-les dans un "
            "sous-dossier pour qu'elles soient importées.",
            len(loose_images),
            args.folder,
        )

    total_events = 0
    total_images = 0
    for subdir in subdirs:
        description, event_date, address = _parse_event_metadata(subdir.name)
        if args.description:
            description = args.description
        if args.event_date:
            event_date = date.fromisoformat(args.event_date)
        if args.address:
            address = args.address

        event = create_event(description, event_date, address)
        logger.info("événement créé : id=%s (%s)", event.id, event.description)
        total_images += _import_folder_for_event(
            subdir, event.id, face_detector, face_embedder, object_storage
        )
        total_events += 1

    logger.info(
        "terminé : %s événement(s), %s image(s) importée(s) et indexée(s) au total",
        total_events,
        total_images,
    )


if __name__ == "__main__":
    main()
