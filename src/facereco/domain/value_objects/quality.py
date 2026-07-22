"""Règles de filtrage qualité des visages détectés (§6.1 du cadrage technique).

Un visage de mauvaise qualité produit un embedding bruité qui génère des faux
positifs sur *toutes* les recherches futures : c'est le levier de précision le
plus rentable du système. Les visages rejetés ne sont jamais ignorés
silencieusement — ils sont persistés avec un statut et un motif, pour mesurer
le taux de couverture réel et ajuster les seuils sur données de production.
"""

from __future__ import annotations

from dataclasses import dataclass

from facereco.domain.value_objects.bounding_box import BoundingBox


@dataclass(frozen=True, slots=True)
class QualityThresholds:
    """Seuils de rejet, valeurs par défaut recommandées par le cadrage technique."""

    min_face_side_px: int = 40
    min_detection_score: float = 0.80
    min_sharpness: float = 60.0
    max_yaw_degrees: float = 45.0


DEFAULT_QUALITY_THRESHOLDS = QualityThresholds()


@dataclass(frozen=True, slots=True)
class QualityAssessment:
    """Résultat de l'évaluation qualité d'un visage détecté."""

    passed: bool
    rejection_reason: str | None = None

    def __post_init__(self) -> None:
        if not self.passed and not self.rejection_reason:
            raise ValueError("Un rejet qualité doit toujours porter un motif.")
        if self.passed and self.rejection_reason:
            raise ValueError("Un visage accepté ne doit pas porter de motif de rejet.")


def assess_face_quality(
    bbox: BoundingBox,
    detection_score: float,
    sharpness: float,
    yaw_degrees: float,
    thresholds: QualityThresholds = DEFAULT_QUALITY_THRESHOLDS,
) -> QualityAssessment:
    """Applique les règles de rejet qualité (§6.1), dans l'ordre : taille, score, netteté, pose."""
    if bbox.side < thresholds.min_face_side_px:
        return QualityAssessment(
            passed=False,
            rejection_reason=f"taille_visage<{thresholds.min_face_side_px}px",
        )
    if detection_score < thresholds.min_detection_score:
        return QualityAssessment(
            passed=False,
            rejection_reason=f"score_detection<{thresholds.min_detection_score}",
        )
    if sharpness < thresholds.min_sharpness:
        return QualityAssessment(passed=False, rejection_reason=f"flou<{thresholds.min_sharpness}")
    if abs(yaw_degrees) > thresholds.max_yaw_degrees:
        return QualityAssessment(
            passed=False,
            rejection_reason=f"pose>{thresholds.max_yaw_degrees}deg",
        )
    return QualityAssessment(passed=True)
