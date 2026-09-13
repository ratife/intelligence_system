"""Test e2e : la route qui adosse l'écran de connexion de l'interface web.

Elle n'a pas de logique propre — elle expose `get_current_actor_id` — mais c'est
précisément le contrat sur lequel le front décide de déverrouiller ou non
l'interface : chaque cas de rejet doit rester un 401 et pas autre chose.
"""

from __future__ import annotations

import pytest

from facereco.infrastructure.config.settings import settings
from tests.e2e.conftest import ACTOR_HEADERS

pytestmark = pytest.mark.e2e

SESSION_URL = "/api/v1/auth/session"


def test_session_returns_actor_id_with_valid_credentials(client) -> None:
    response = client.get(SESSION_URL, headers=ACTOR_HEADERS)

    assert response.status_code == 200
    assert response.json() == {"actor_id": "e2e-test"}


def test_session_rejects_wrong_token(client) -> None:
    response = client.get(
        SESSION_URL,
        headers={"Authorization": "Bearer mauvais-jeton", "X-Actor-Id": "e2e-test"},
    )

    assert response.status_code == 401


def test_session_rejects_non_bearer_scheme(client) -> None:
    response = client.get(
        SESSION_URL,
        headers={"Authorization": f"Basic {settings.api_bearer_token}", "X-Actor-Id": "e2e-test"},
    )

    assert response.status_code == 401


def test_session_rejects_blank_actor_id(client) -> None:
    response = client.get(
        SESSION_URL,
        headers={"Authorization": f"Bearer {settings.api_bearer_token}", "X-Actor-Id": "   "},
    )

    assert response.status_code == 401


def test_session_rejects_missing_headers_as_validation_error(client) -> None:
    """En-têtes absents → 422, pas 401.

    Les en-têtes sont déclarés requis dans `get_current_actor_id`, donc FastAPI
    rejette avant d'atteindre la vérification du jeton. Comportement pré-existant
    et partagé par toutes les routes authentifiées : on le fige plutôt que de le
    modifier ici. L'écran de connexion envoie toujours les deux en-têtes, il ne
    rencontre donc que le 401.
    """
    response = client.get(SESSION_URL)

    assert response.status_code == 422
