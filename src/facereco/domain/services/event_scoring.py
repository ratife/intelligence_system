"""Agrégation des visages candidats en score d'événement (ADR 006, §7.2).

Fonction retenue : score = max(similarité) + λ·log(1 + n_matches).
Le max seul est trop sensible à un unique faux positif ; la moyenne dilue le
signal d'un événement avec beaucoup de visages peu pertinents. Le bonus
logarithmique de corroboration récompense la répétition (une personne présente
sur plusieurs photos d'un même événement) sans jamais écraser le signal
principal porté par le meilleur match.
"""

from __future__ import annotations

import math
from collections import defaultdict

from facereco.domain.entities.search import EventMatch, FaceCandidate

DEFAULT_CORROBORATION_LAMBDA = 0.02


def aggregate_matches_by_event(
    candidates: list[FaceCandidate],
    corroboration_lambda: float = DEFAULT_CORROBORATION_LAMBDA,
) -> list[EventMatch]:
    """Regroupe les visages candidats par événement et calcule le score agrégé.

    Précondition : ``candidates`` ne contient que des visages déjà passés le
    seuil de similarité (le seuillage est une étape distincte, en amont).
    """
    grouped: dict[int, list[FaceCandidate]] = defaultdict(list)
    for candidate in candidates:
        grouped[candidate.event.id].append(candidate)

    matches: list[EventMatch] = []
    for group in grouped.values():
        best = max(group, key=lambda c: c.similarity)
        score = best.similarity + corroboration_lambda * math.log(1 + len(group))
        matches.append(
            EventMatch(
                event=best.event,
                confidence=score,
                match_count=len(group),
                evidence=best.evidence,
            )
        )

    matches.sort(key=lambda m: m.confidence, reverse=True)
    return matches
