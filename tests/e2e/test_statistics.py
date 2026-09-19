"""Test e2e du tableau de bord : les agrégats sont calculés sur une vraie base.

L'intérêt n'est pas la route (triviale) mais la requête d'agrégation : chaque
compteur doit viser la bonne table avec le bon filtre, et les taux dérivés
doivent retomber sur les valeurs attendues à partir de données connues.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.e2e.conftest import ACTOR_HEADERS

pytestmark = pytest.mark.e2e

STATS_URL = "/api/v1/stats"


def _seed(session) -> None:
    """3 images : 2 indexées, 1 en attente. 3 visages retenus, 1 écarté. 3 recherches, 1 vide."""
    session.execute(
        text(
            "INSERT INTO events (id, title, description, event_date, address) VALUES "
            "(1, 'Séminaire', '', '2026-03-14', 'Antananarivo'), "
            "(2, 'Conférence', '', '2026-04-01', 'Fianarantsoa')"
        )
    )
    session.execute(
        text(
            "INSERT INTO event_images (id, event_id, storage_uri, content_hash, index_status) "
            "VALUES "
            "(1, 1, 's3://b/a.jpg', 'hash-a', 'done'), "
            "(2, 1, 's3://b/b.jpg', 'hash-b', 'done'), "
            "(3, 2, 's3://b/c.jpg', 'hash-c', 'pending')"
        )
    )
    session.execute(
        text(
            "INSERT INTO face_embeddings "
            "(image_id, event_id, face_index, bbox, det_score, quality_score, embedding, "
            " model_version, created_at) VALUES "
            "(1, 1, 0, '{0,0,10,10}', 0.9, 0.9, :vec, 'arcface-r100-v1', now()), "
            "(1, 1, 1, '{0,0,10,10}', 0.9, 0.9, :vec, 'arcface-r100-v1', now()), "
            "(2, 1, 0, '{0,0,10,10}', 0.9, 0.9, :vec, 'arcface-r100-v1', now())"
        ),
        {"vec": "[" + ",".join(["0.0"] * 511) + ",1.0]"},
    )
    session.execute(
        text(
            "INSERT INTO rejected_faces (image_id, face_index, rejection_reason, created_at) "
            "VALUES (2, 1, 'visage_trop_petit', now())"
        )
    )
    session.execute(
        text(
            "INSERT INTO search_audit_log "
            "(actor_id, query_hash, result_count, top_score, threshold_used, model_version, "
            " created_at) VALUES "
            "('alice', 'h1', 2, 0.80, 0.38, 'arcface-r100-v1', now()), "
            "('alice', 'h2', 1, 0.60, 0.38, 'arcface-r100-v1', now()), "
            "('bob',   'h3', 0, NULL, 0.38, 'arcface-r100-v1', now())"
        )
    )
    session.commit()


@pytest.fixture()
def seeded(test_app):
    from facereco.infrastructure.db.session import SessionFactory

    session = SessionFactory()
    try:
        _seed(session)
    finally:
        session.close()
    return test_app


def test_statistics_reports_volumes_and_derived_rates(seeded, client) -> None:
    body = client.get(STATS_URL, headers=ACTOR_HEADERS).json()

    assert body["event_count"] == 2
    assert body["image_count"] == 3
    assert body["indexed_image_count"] == 2
    assert body["pending_image_count"] == 1
    assert body["face_count"] == 3
    assert body["rejected_face_count"] == 1
    assert body["detected_face_count"] == 4

    assert body["indexing_completion_rate"] == pytest.approx(2 / 3)
    assert body["quality_rejection_rate"] == pytest.approx(0.25)
    assert body["average_faces_per_indexed_image"] == pytest.approx(1.5)


def test_statistics_reports_search_activity(seeded, client) -> None:
    body = client.get(STATS_URL, headers=ACTOR_HEADERS).json()

    assert body["search_count"] == 3
    assert body["empty_search_count"] == 1
    assert body["distinct_actor_count"] == 2
    assert body["empty_search_rate"] == pytest.approx(1 / 3)
    # Moyenne sur les seules recherches abouties : (0.80 + 0.60) / 2, pas / 3.
    assert body["average_top_score"] == pytest.approx(0.70, abs=1e-6)


def test_statistics_breaks_down_rejections_and_model_versions(seeded, client) -> None:
    body = client.get(STATS_URL, headers=ACTOR_HEADERS).json()

    assert body["rejections_by_reason"] == [{"reason": "visage_trop_petit", "count": 1}]
    assert body["model_versions"] == ["arcface-r100-v1"]


def test_statistics_on_empty_system_returns_zeroes(client) -> None:
    """Aucune donnée : des zéros, pas une division par zéro."""
    body = client.get(STATS_URL, headers=ACTOR_HEADERS).json()

    assert body["image_count"] == 0
    assert body["indexing_completion_rate"] == 0.0
    assert body["quality_rejection_rate"] == 0.0
    assert body["average_top_score"] is None
    assert body["rejections_by_reason"] == []


def test_statistics_requires_authentication(client) -> None:
    response = client.get(
        STATS_URL, headers={"Authorization": "Bearer mauvais", "X-Actor-Id": "alice"}
    )

    assert response.status_code == 401


def test_a_face_discarded_several_times_is_counted_once(seeded, client) -> None:
    """`rejected_faces` accumule des doublons ; le taux de rejet ne doit pas les suivre.

    La table n'a pas de contrainte d'unicité, et une image dont tous les visages
    ont été écartés reste éligible à l'indexation (aucune empreinte pour la
    version de modèle courante) : chaque relance y réinsère les mêmes rejets.
    Sur les données de développement, cela gonflait le compteur d'un facteur
    3,75 — soit 91 % de rejet affiché pour 74 % réels, sur l'indicateur qui sert
    précisément à régler les seuils du filtre qualité (§6.1).
    """
    from facereco.infrastructure.db.session import SessionFactory

    session = SessionFactory()
    try:
        # Le visage (2, 1) est déjà écarté une fois par le jeu de données.
        session.execute(
            text(
                "INSERT INTO rejected_faces (image_id, face_index, rejection_reason, created_at) "
                "VALUES (2, 1, 'visage_trop_petit', now()), "
                "(2, 1, 'visage_trop_petit', now())"
            )
        )
        session.commit()
    finally:
        session.close()

    body = client.get(STATS_URL, headers=ACTOR_HEADERS).json()

    assert body["rejected_face_count"] == 1
    assert body["rejections_by_reason"] == [{"reason": "visage_trop_petit", "count": 1}]
    # 3 visages retenus + 1 écarté : le taux ne bouge pas malgré les 3 lignes.
    assert body["quality_rejection_rate"] == pytest.approx(0.25)
