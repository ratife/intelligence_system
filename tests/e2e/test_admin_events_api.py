"""Création d'événement — `POST /api/v1/admin/events`.

Cette route n'avait aucune couverture : son router n'était pas monté dans
l'application de test, alors qu'il l'est en production. Elle est pourtant le
seul point d'entrée en écriture de l'interface web, et c'est sa requête que
l'ajout de `title` modifie.

L'import d'images (`POST /{id}/images`) reste hors de portée ici : il exige un
vrai stockage objet.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from sqlalchemy import text

from tests.e2e.conftest import ACTOR_HEADERS

pytestmark = pytest.mark.e2e

PATH = "/api/v1/admin/events"


def test_creates_event_with_title_and_description(client: TestClient) -> None:
    response = client.post(
        PATH,
        headers=ACTOR_HEADERS,
        json={
            "title": "Assemblée générale",
            "description": "Restitution annuelle et élection du bureau.",
            "event_date": "2026-03-14",
            "address": "Antananarivo",
        },
    )

    assert response.status_code == 201
    body = response.json()
    assert body["title"] == "Assemblée générale"
    assert body["description"] == "Restitution annuelle et élection du bureau."

    # Relu en base et pas seulement dans la réponse : c'est le seul test qui
    # couvre `create_event`, qui écrit en contournant les ports du domaine.
    from facereco.infrastructure.db.session import SessionFactory

    session = SessionFactory()
    try:
        row = session.execute(
            text("SELECT title, description FROM events WHERE id = :id"), {"id": body["id"]}
        ).one()
    finally:
        session.close()
    assert row.title == "Assemblée générale"
    assert row.description == "Restitution annuelle et élection du bureau."


def test_description_is_optional(client: TestClient) -> None:
    """Un événement doit pouvoir être créé sans qu'on rédige un paragraphe."""
    response = client.post(
        PATH,
        headers=ACTOR_HEADERS,
        json={"title": "Conférence", "event_date": "2026-04-01", "address": "Fianarantsoa"},
    )

    assert response.status_code == 201
    assert response.json()["description"] == ""


def test_long_multiline_description_survives_round_trip(client: TestClient) -> None:
    """La description est un texte long : ni tronquée, ni aplatie.

    Les retours à la ligne comptent autant que la longueur — c'est eux que la
    fiche détail réaffiche, et une colonne mal typée les perdrait en silence.
    """
    description = "\n\n".join(f"Paragraphe {n} de compte rendu." for n in range(1, 40))

    response = client.post(
        PATH,
        headers=ACTOR_HEADERS,
        json={
            "title": "Séminaire",
            "description": description,
            "event_date": "2026-05-02",
            "address": "Mahajanga",
        },
    )

    assert response.status_code == 201
    assert response.json()["description"] == description


@pytest.mark.parametrize(
    ("payload", "raison"),
    [
        ({"event_date": "2026-03-14", "address": "Antananarivo"}, "titre absent"),
        ({"title": "", "event_date": "2026-03-14", "address": "Antananarivo"}, "titre vide"),
        ({"title": "   ", "event_date": "2026-03-14", "address": "Antananarivo"}, "titre blanc"),
    ],
)
def test_rejects_event_without_usable_title(client: TestClient, payload, raison: str) -> None:
    """Le cas « titre blanc » est le seul qui prouve `strip_whitespace`.

    Sans lui, `min_length=1` laisse passer une suite d'espaces et l'événement
    se retrouve sans intitulé lisible dans les listes.
    """
    response = client.post(PATH, headers=ACTOR_HEADERS, json=payload)
    assert response.status_code == 422, raison


def test_title_is_trimmed(client: TestClient) -> None:
    response = client.post(
        PATH,
        headers=ACTOR_HEADERS,
        json={"title": "  Gala  ", "event_date": "2026-07-01", "address": "Toamasina"},
    )

    assert response.status_code == 201
    assert response.json()["title"] == "Gala"


def test_rejects_invalid_token(client: TestClient) -> None:
    """Créer un événement exige un jeton valide.

    À noter : des en-têtes *absents* donnent 422 et non 401, les deux étant
    déclarés obligatoires par FastAPI. C'est le contrat existant de toutes les
    routes protégées, pas une particularité de celle-ci.
    """
    response = client.post(
        PATH,
        headers={"Authorization": "Bearer mauvais-jeton", "X-Actor-Id": "e2e-test"},
        json={"title": "Gala", "event_date": "2026-07-01", "address": "Toamasina"},
    )
    assert response.status_code == 401
