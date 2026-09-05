"""Photographie chiffrée de l'état du système — modèle de lecture du tableau de bord.

Les compteurs bruts viennent de l'infrastructure ; les **taux** sont calculés
ici, parce qu'ils portent des décisions de lecture qui n'appartiennent ni à SQL
ni à l'affichage : que vaut un taux de rejet quand aucun visage n'a été détecté,
sur quel dénominateur se calcule le taux de rejet qualité (visages *détectés*,
pas images), etc.

Deux indicateurs méritent une attention particulière :

- `quality_rejection_rate` rend mesurable le filtre qualité (§6.1) : les rejets
  ne sont jamais silencieux, encore faut-il pouvoir les regarder pour régler les
  seuils.
- `empty_search_rate` et `average_top_score` éclairent le seuil de similarité,
  dont le défaut (0.38) est explicitement non calibré tant qu'aucune campagne
  sur données réelles n'a été menée (§10.2). Un taux de recherches vides élevé
  est le premier signal d'un seuil trop haut.

Note de périmètre : ceci est un modèle de lecture, pas de l'observabilité au
sens du Lot 3 (métriques, traces, alertes) — délibérément non implémenté.
"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True, slots=True)
class RejectionReasonCount:
    """Nombre de visages écartés pour un motif donné (`quality.py`)."""

    reason: str
    count: int

    def __post_init__(self) -> None:
        if self.count < 0:
            raise ValueError(f"Compteur négatif pour le motif {self.reason!r} : {self.count}.")


@dataclass(frozen=True, slots=True)
class SystemStatistics:
    """Compteurs bruts du système, et taux qui s'en déduisent."""

    event_count: int
    image_count: int
    indexed_image_count: int
    pending_image_count: int
    face_count: int
    rejected_face_count: int
    search_count: int
    empty_search_count: int
    distinct_actor_count: int
    average_top_score: float | None
    rejections_by_reason: tuple[RejectionReasonCount, ...] = ()
    model_versions: tuple[str, ...] = field(default=())

    def __post_init__(self) -> None:
        counters = {
            "event_count": self.event_count,
            "image_count": self.image_count,
            "indexed_image_count": self.indexed_image_count,
            "pending_image_count": self.pending_image_count,
            "face_count": self.face_count,
            "rejected_face_count": self.rejected_face_count,
            "search_count": self.search_count,
            "empty_search_count": self.empty_search_count,
            "distinct_actor_count": self.distinct_actor_count,
        }
        for name, value in counters.items():
            if value < 0:
                raise ValueError(f"{name} ne peut pas être négatif, reçu {value}.")
        # Un sous-ensemble ne peut pas dépasser son ensemble : si l'un de ces
        # invariants casse, c'est la requête d'agrégation qui est fausse, et il
        # vaut mieux le voir tout de suite qu'afficher un taux au-dessus de 100 %.
        if self.indexed_image_count > self.image_count:
            raise ValueError(
                f"indexed_image_count ({self.indexed_image_count}) dépasse "
                f"image_count ({self.image_count})."
            )
        if self.empty_search_count > self.search_count:
            raise ValueError(
                f"empty_search_count ({self.empty_search_count}) dépasse "
                f"search_count ({self.search_count})."
            )

    @property
    def detected_face_count(self) -> int:
        """Visages détectés = retenus + écartés par le filtre qualité."""
        return self.face_count + self.rejected_face_count

    @property
    def indexing_completion_rate(self) -> float:
        """Part des images dont l'indexation est terminée (0.0 → 1.0)."""
        return self._ratio(self.indexed_image_count, self.image_count)

    @property
    def quality_rejection_rate(self) -> float:
        """Part des visages *détectés* écartés par le filtre qualité (§6.1)."""
        return self._ratio(self.rejected_face_count, self.detected_face_count)

    @property
    def average_faces_per_indexed_image(self) -> float:
        """Densité de visages : rapportée aux images indexées, pas au total.

        Rapporter au total mélangerait les images en attente, qui n'ont encore
        produit aucun visage, et écraserait artificiellement la moyenne.
        """
        return self._ratio(self.face_count, self.indexed_image_count)

    @property
    def empty_search_rate(self) -> float:
        """Part des recherches n'ayant retourné aucun événement (§10.2)."""
        return self._ratio(self.empty_search_count, self.search_count)

    @staticmethod
    def _ratio(numerator: int, denominator: int) -> float:
        """Un ratio sans dénominateur vaut 0.0 : « rien à mesurer », pas une erreur."""
        return 0.0 if denominator == 0 else numerator / denominator
