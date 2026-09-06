"""Use case de préparation d'une recherche : quels visages contient cette image ?

Le pipeline de recherche refuse de deviner quand plusieurs visages sont présents
(`AmbiguousFaceSelectionError`, §7.1) — l'appelant doit désigner `face_index`.
Encore faut-il qu'il puisse savoir à quoi correspond chaque index : c'est
l'objet de ce use case, qui rend les visages *situables* (leurs cadres) avant
toute recherche, pour que la désignation soit un choix éclairé et non un tirage.

Volontairement en retrait du pipeline de recherche :

- **pas de quota** — le quota protège contre la surveillance de masse en
  limitant les interrogations de la base ; ici rien n'est interrogé. Le
  décompter ferait consommer à l'opérateur son budget de recherche juste pour
  afficher des cadres, avant même d'avoir cherché quoi que ce soit ;
- **pas de journal d'audit** — aucune donnée indexée n'est consultée, il n'y a
  donc pas de recherche à tracer (ADR 008 vise les recherches, pas les
  détections) ;
- **aucun filtrage qualité** — le seuil qualité s'applique à l'indexation, pas
  au visage requête. Afficher un verdict « rejeté » ici laisserait croire à une
  barrière qui n'existe pas côté recherche.

Le détecteur est le port partagé avec l'indexation : les cadres affichés sont
exactement ceux que la recherche utilisera, sans second chemin de
pré-traitement (§5, « piège classique n°1 »).
"""

from __future__ import annotations

from facereco.application.dto import DetectQueryFacesCommand
from facereco.domain.entities.face import DetectedFace
from facereco.domain.ports.face_detector import FaceDetectorPort


class DetectQueryFacesUseCase:
    def __init__(self, face_detector: FaceDetectorPort) -> None:
        self._face_detector = face_detector

    def execute(self, command: DetectQueryFacesCommand) -> list[DetectedFace]:
        """Les visages dans l'ordre du détecteur — l'index de position fait foi.

        Une image sans visage renvoie une liste vide plutôt qu'une erreur : la
        question posée est « que contient cette image », et « rien » y est une
        réponse valide. C'est la recherche, elle, qui échoue en 409.
        """
        return self._face_detector.detect_faces(command.query_image_bytes)
