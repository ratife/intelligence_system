"""Outil de test manuel du pipeline d'indexation sur un dossier d'images local.

Exécute détection → filtre qualité → embedding pour chaque image d'un dossier,
en réutilisant les mêmes adapters ML que la production (`InsightFaceDetector`,
`ArcFaceEmbedder`) et les mêmes règles de qualité (`assess_face_quality`) —
sans persistance ni rattachement à un `Event` : cet outil sert uniquement à
valider le comportement de détection/qualité/embedding sur des images
arbitraires, avant de les faire transiter par le pipeline complet (worker +
Postgres + Event/EventImage).

Usage :
    python -m facereco.interface.cli.index_folder /chemin/vers/dossier
"""

from __future__ import annotations

import argparse
import logging
from pathlib import Path

from facereco.domain.value_objects.quality import DEFAULT_QUALITY_THRESHOLDS, assess_face_quality
from facereco.infrastructure.config.settings import settings
from facereco.infrastructure.ml.arcface_embedder import ArcFaceEmbedder
from facereco.infrastructure.ml.insightface_detector import InsightFaceDetector

logger = logging.getLogger("facereco.cli.index_folder")

IMAGE_EXTENSIONS = {".jpg", ".jpeg", ".png", ".bmp", ".webp"}


def iter_image_paths(folder: Path) -> list[Path]:
    return sorted(
        path
        for path in folder.iterdir()
        if path.is_file() and path.suffix.lower() in IMAGE_EXTENSIONS
    )


def run(folder: Path) -> None:
    image_paths = iter_image_paths(folder)
    if not image_paths:
        logger.warning(
            "aucune image trouvée dans %s (extensions attendues : %s)",
            folder,
            sorted(IMAGE_EXTENSIONS),
        )
        return

    detector = InsightFaceDetector(
        model_pack=settings.insightface_model_pack, providers=settings.onnx_providers
    )
    embedder = ArcFaceEmbedder(
        model_pack=settings.insightface_model_pack,
        providers=settings.onnx_providers,
        version=settings.model_version,
    )

    total_accepted = 0
    total_rejected = 0

    for path in image_paths:
        image_bytes = path.read_bytes()
        try:
            faces = detector.detect_faces(image_bytes)
        except ValueError as exc:
            logger.error("%s : image illisible (%s)", path.name, exc)
            continue

        if not faces:
            logger.info("%s : aucun visage détecté", path.name)
            continue

        for face_index, face in enumerate(faces):
            assessment = assess_face_quality(
                bbox=face.bbox,
                detection_score=face.detection_score,
                sharpness=face.sharpness,
                yaw_degrees=face.yaw_degrees,
                thresholds=DEFAULT_QUALITY_THRESHOLDS,
            )
            if not assessment.passed:
                total_rejected += 1
                logger.info(
                    "%s : visage #%s rejeté (%s) — score=%.3f netteté=%.1f yaw=%.1f°",
                    path.name,
                    face_index,
                    assessment.rejection_reason,
                    face.detection_score,
                    face.sharpness,
                    face.yaw_degrees,
                )
                continue

            embedding = embedder.compute_embedding(image_bytes, face)
            total_accepted += 1
            logger.info(
                "%s : visage #%s accepté — score=%.3f bbox=%s embedding_dim=%s",
                path.name,
                face_index,
                face.detection_score,
                face.bbox.as_tuple(),
                len(embedding.values),
            )

    logger.info(
        "terminé : %s image(s) traitée(s), %s visage(s) accepté(s), %s rejeté(s)",
        len(image_paths),
        total_accepted,
        total_rejected,
    )


def main() -> None:
    parser = argparse.ArgumentParser(
        description=(
            "Teste le pipeline détection/qualité/embedding sur un dossier d'images "
            "local, sans base de données ni rattachement à un événement."
        )
    )
    parser.add_argument("folder", type=Path, help="Dossier contenant les images à traiter.")
    args = parser.parse_args()

    if not args.folder.is_dir():
        parser.error(f"{args.folder} n'est pas un dossier.")

    logging.basicConfig(level=logging.INFO, format="%(message)s")
    run(args.folder)


if __name__ == "__main__":
    main()
