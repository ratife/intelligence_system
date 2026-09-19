"""Propriétés des migrations elles-mêmes.

Deux garanties que rien d'autre ne vérifie, et dont la seconde décrit exactement
ce qui se passera sur une base déjà en service.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from tests.db_schema import apply_migrations

pytestmark = pytest.mark.integration


def test_migrations_are_replayable(db_engine) -> None:
    """Rejouer toutes les migrations ne doit rien casser.

    Ce n'est pas une élégance : la fixture `test_app` des tests e2e les applique
    à *chaque* test sur un conteneur partagé par le module. Une migration non
    rejouable ferait échouer le deuxième test venu, et l'erreur désignerait le
    test plutôt que la migration.
    """
    apply_migrations(db_engine)
    apply_migrations(db_engine)

    with db_engine.begin() as connection:
        columns = connection.execute(
            text(
                "SELECT column_name FROM information_schema.columns "
                "WHERE table_name = 'events' ORDER BY column_name"
            )
        ).scalars()
    assert list(columns) == ["address", "description", "event_date", "id", "title"]


def test_title_is_backfilled_from_description(db_engine) -> None:
    """Reprise des lignes antérieures à `title`, telle qu'elle aura lieu en production.

    On reconstitue l'état d'avant (colonne retirée), on insère des lignes comme
    le faisait l'ancien schéma, puis on rejoue les migrations. C'est le seul
    test qui exerce le chemin réel du VPS, où la table n'est pas vide.
    """
    with db_engine.begin() as connection:
        connection.execute(text("DELETE FROM events"))
        connection.execute(text("ALTER TABLE events DROP COLUMN title"))
        connection.execute(
            text(
                "INSERT INTO events (id, description, event_date, address) VALUES "
                "(901, 'Assemblée générale', '2026-03-14', 'Antananarivo'), "
                "(902, '', '2026-04-01', 'Toamasina'), "
                "(903, 'Première ligne" + chr(10) + "seconde ligne', '2026-05-02', 'Mahajanga')"
            )
        )

    apply_migrations(db_engine)

    with db_engine.begin() as connection:
        rows = connection.execute(
            text("SELECT id, title FROM events WHERE id BETWEEN 901 AND 903 ORDER BY id")
        ).all()
        nullable = connection.execute(
            text(
                "SELECT is_nullable FROM information_schema.columns "
                "WHERE table_name = 'events' AND column_name = 'title'"
            )
        ).scalar_one()

    titles = {row.id: row.title for row in rows}
    assert titles[901] == "Assemblée générale"
    # Description vide : sans repli, le passage en NOT NULL échouerait ici.
    assert titles[902] == "Événement 902"
    # Description multi-ligne : seule la première ligne fait un intitulé.
    assert titles[903] == "Première ligne"
    assert nullable == "NO"
