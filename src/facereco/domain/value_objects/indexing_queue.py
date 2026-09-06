"""État de la file d'indexation et de ses workers — modèle de lecture.

Ce que la file sait, et ce qu'elle ne sait pas : Redis Streams enregistre des
**consommateurs**, pas des processus. Une entrée de consommateur survit à la mort
du worker qui l'a créée, et rien n'y indique « vivant » ou « arrêté ». La seule
information disponible est de l'**activité** : depuis combien de temps ce
consommateur a interrogé la file (`idle`), et depuis combien de temps il a
réellement lu un message (`inactive`).

D'où le vocabulaire retenu ici : on parle de consommateur *actif* ou *silencieux*
selon la fraîcheur de son dernier sondage, jamais de worker « démarré ». Un
consommateur silencieux est soit un processus mort, soit un processus vivant sans
travail — la file ne permet pas de trancher, et l'interface ne doit pas prétendre
le contraire.
"""

from __future__ import annotations

from dataclasses import dataclass

# Le worker sonde toutes les 2 s (`POLL_INTERVAL_SECONDS`). Au-delà de quinze
# fois cet intervalle sans le moindre sondage, le consommateur n'est plus
# considéré comme actif — marge large, pour qu'une image longue à traiter ou une
# machine chargée ne le fasse pas basculer à tort.
ACTIVE_IDLE_THRESHOLD_SECONDS = 30.0


@dataclass(frozen=True, slots=True)
class WorkerStatus:
    """Un consommateur enregistré dans le groupe, vu par la file."""

    name: str
    """Nom du consommateur. Deux processus partageant un nom sont indiscernables
    et se disputent les mêmes messages : le worker en dérive donc un unique."""

    pending_messages: int
    """Messages qui lui ont été remis et qu'il n'a pas encore acquittés."""

    idle_seconds: float
    """Depuis son dernier échange avec la file — le signal de vie disponible."""

    inactive_seconds: float
    """Depuis sa dernière lecture réussie. Élevé sans être anormal : un worker
    vivant mais sans travail n'a rien à lire."""

    def __post_init__(self) -> None:
        if not self.name:
            raise ValueError("WorkerStatus: nom de consommateur vide.")
        if self.pending_messages < 0:
            raise ValueError(f"WorkerStatus: pending_messages négatif ({self.pending_messages}).")
        if self.idle_seconds < 0 or self.inactive_seconds < 0:
            raise ValueError("WorkerStatus: les durées d'inactivité ne peuvent être négatives.")

    @property
    def is_active(self) -> bool:
        """A sondé la file récemment. Ne dit pas qu'il traite quelque chose."""
        return self.idle_seconds < ACTIVE_IDLE_THRESHOLD_SECONDS

    @property
    def is_working(self) -> bool:
        """Détient au moins un message non acquitté : il a du travail en cours."""
        return self.pending_messages > 0


@dataclass(frozen=True, slots=True)
class IndexingQueueStatus:
    """Photographie de la file d'indexation et de ses consommateurs."""

    consumer_group: str
    workers: tuple[WorkerStatus, ...]
    undelivered_messages: int
    """Messages publiés que le groupe n'a encore remis à personne (le retard)."""

    unacknowledged_messages: int
    """Messages remis à un consommateur et pas encore acquittés."""

    dead_letter_messages: int
    """Messages abandonnés après épuisement des tentatives (§6.1)."""

    def __post_init__(self) -> None:
        counters = {
            "undelivered_messages": self.undelivered_messages,
            "unacknowledged_messages": self.unacknowledged_messages,
            "dead_letter_messages": self.dead_letter_messages,
        }
        for name, value in counters.items():
            if value < 0:
                raise ValueError(f"{name} ne peut pas être négatif, reçu {value}.")

    @property
    def active_workers(self) -> tuple[WorkerStatus, ...]:
        return tuple(worker for worker in self.workers if worker.is_active)

    @property
    def backlog(self) -> int:
        """Travail restant : ni remis, ou remis mais pas encore acquitté."""
        return self.undelivered_messages + self.unacknowledged_messages

    @property
    def is_stalled(self) -> bool:
        """Du travail en attente, et personne pour le prendre.

        C'est le diagnostic utile à afficher : une file qui se remplit sans
        consommateur actif est un worker à démarrer, pas une lenteur.
        """
        return self.backlog > 0 and not self.active_workers

    @property
    def has_dead_letters(self) -> bool:
        return self.dead_letter_messages > 0
