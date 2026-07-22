"""Exceptions métier du domaine — aucune dépendance à un framework ou protocole de transport.

La couche Interface (FastAPI) est responsable de traduire ces exceptions en codes HTTP.
"""

from __future__ import annotations


class DomainError(Exception):
    """Racine de toutes les erreurs métier."""


class NoFaceDetectedError(DomainError):
    """Aucun visage n'a été détecté dans l'image soumise."""


class AmbiguousFaceSelectionError(DomainError):
    """Plusieurs visages détectés dans l'image requête sans indication du visage à utiliser.

    Le système ne doit jamais deviner silencieusement (cf. §7.1 du cadrage technique) :
    l'appelant doit désigner explicitement le visage voulu via ``face_index``.
    """

    def __init__(self, faces_detected: int) -> None:
        self.faces_detected = faces_detected
        super().__init__(
            f"{faces_detected} visages détectés dans l'image requête : "
            "précisez face_index pour désambiguïser."
        )


class InvalidFaceIndexError(DomainError):
    """L'index de visage désigné par l'appelant est hors bornes."""

    def __init__(self, face_index: int, faces_detected: int) -> None:
        self.face_index = face_index
        self.faces_detected = faces_detected
        super().__init__(
            f"face_index={face_index} invalide pour {faces_detected} visage(s) détecté(s)."
        )


class ImageQualityRejectedError(DomainError):
    """L'image ou le visage extrait ne satisfait pas les critères de qualité minimaux."""

    def __init__(self, reason: str) -> None:
        self.reason = reason
        super().__init__(f"Image rejetée pour qualité insuffisante : {reason}")


class EventNotFoundError(DomainError):
    """Référence à un événement inexistant."""

    def __init__(self, event_id: int) -> None:
        self.event_id = event_id
        super().__init__(f"Événement {event_id} introuvable.")


class SearchQuotaExceededError(DomainError):
    """L'acteur a dépassé son quota de recherches (protection anti-surveillance de masse)."""

    def __init__(self, actor_id: str) -> None:
        self.actor_id = actor_id
        super().__init__(f"Quota de recherche dépassé pour l'acteur {actor_id}.")
