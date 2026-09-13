"""Test e2e : POST /api/v1/search/faces — situer les visages avant de chercher.

Cette route existe pour qu'un opérateur puisse *voir* à quoi correspond chaque
`face_index` : les tests portent donc sur ce qui rend cet affichage fiable —
la numérotation par position et la restitution fidèle des cadres.
"""

from __future__ import annotations

import pytest

from tests.e2e.conftest import ACTOR_HEADERS, GROUP_PHOTO_BYTES

pytestmark = pytest.mark.e2e

PHOTO_BYTES = b"query-image-bytes"  # doit correspondre à `query_image` du conftest e2e


def test_returns_one_numbered_box_per_detected_face(client) -> None:
    response = client.post(
        "/api/v1/search/faces",
        headers=ACTOR_HEADERS,
        files={"image": ("groupe.jpg", GROUP_PHOTO_BYTES, "image/jpeg")},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["faces_detected"] == 2
    # L'index est la position dans la liste du détecteur — c'est exactement ce
    # que `face_index` attend côté recherche. Un décalage ici ferait chercher un
    # autre visage que celui encadré à l'écran.
    assert [face["index"] for face in body["faces"]] == [0, 1]
    assert body["faces"][0]["bbox"] == [10, 20, 100, 100]
    assert body["faces"][1]["bbox"] == [300, 40, 80, 80]
    assert body["faces"][1]["quality"] == pytest.approx(0.62)


def test_index_returned_here_is_the_one_search_accepts(client) -> None:
    """Le contrat qui lie les deux routes : l'index affiché doit être cherchable.

    Sans lui, l'interface encadrerait des visages qu'on ne peut pas désigner —
    et la photo de groupe resterait le mur qu'elle est aujourd'hui (409).
    """
    faces = client.post(
        "/api/v1/search/faces",
        headers=ACTOR_HEADERS,
        files={"image": ("groupe.jpg", GROUP_PHOTO_BYTES, "image/jpeg")},
    ).json()["faces"]

    response = client.post(
        "/api/v1/search/by-face",
        headers=ACTOR_HEADERS,
        files={"image": ("groupe.jpg", GROUP_PHOTO_BYTES, "image/jpeg")},
        data={"face_index": faces[1]["index"]},
    )

    assert response.status_code == 200
    used = response.json()["query"]["face_used"]
    assert used["index"] == 1
    assert used["bbox"] == faces[1]["bbox"]


def test_image_without_face_answers_zero_rather_than_erroring(client) -> None:
    """La recherche répond 409 sur une image sans visage ; la détection décrit."""
    response = client.post(
        "/api/v1/search/faces",
        headers=ACTOR_HEADERS,
        files={"image": ("vide.jpg", b"unknown-bytes-without-face", "image/jpeg")},
    )

    assert response.status_code == 200
    assert response.json() == {"faces_detected": 0, "faces": []}


def test_requires_authentication(client) -> None:
    """422 et non 401 : `Authorization`/`X-Actor-Id` sont des en-têtes déclarés
    obligatoires, FastAPI rejette donc la requête avant d'atteindre la
    vérification du jeton. Comportement identique à /by-face."""
    response = client.post(
        "/api/v1/search/faces",
        files={"image": ("photo.jpg", PHOTO_BYTES, "image/jpeg")},
    )

    assert response.status_code == 422
