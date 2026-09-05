"""Vérification des identifiants — adosse l'écran de connexion de l'interface web.

Aucune logique d'authentification ici : toute la vérification vit déjà dans
`get_current_actor_id` (`interface/api/deps.py`). Cette route ne fait que
l'exposer, pour que le front puisse valider un couple identifiant/jeton sans
avoir à sonder une route métier (et donc sans rapatrier de données au passage).

Rappel du niveau de garantie (§13, README) : un jeton unique partagé n'est pas
un IAM. Cette route confirme que le jeton est le bon, rien de plus.
"""

from __future__ import annotations

from typing import Annotated

from fastapi import APIRouter, Depends
from pydantic import BaseModel

from facereco.interface.api.deps import get_current_actor_id

router = APIRouter(prefix="/api/v1/auth", tags=["auth"])


class SessionSchema(BaseModel):
    actor_id: str


@router.get("/session", response_model=SessionSchema)
async def get_session(
    actor_id: Annotated[str, Depends(get_current_actor_id)],
) -> SessionSchema:
    """200 si les identifiants sont valides, 401 sinon (levé par la dépendance)."""
    return SessionSchema(actor_id=actor_id)
