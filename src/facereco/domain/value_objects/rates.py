"""Règle de lecture commune aux taux des modèles de lecture.

Extraite parce qu'elle est partagée : un même indicateur (le taux de rejet
qualité, l'avancement d'indexation) apparaît sur le tableau de bord *et* sur le
catalogue d'événements. Les faire dépendre de la même fonction est ce qui
garantit qu'ils ne divergeront pas d'un écran à l'autre.
"""

from __future__ import annotations


def read_rate(numerator: int, denominator: int) -> float:
    """Un taux sans dénominateur vaut 0.0 : « rien à mesurer », pas une erreur.

    Une installation neuve doit s'afficher, pas tomber en division par zéro.
    """
    return 0.0 if denominator == 0 else numerator / denominator
