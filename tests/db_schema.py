"""Application du schéma SQL aux bases de test.

Partagé par les fixtures d'intégration et de bout en bout, qui codaient jusqu'ici
chacune en dur le chemin de `0001_init.sql`. Une migration ajoutée n'était donc
lue par aucune des deux, et la divergence était silencieuse : les tests
continuaient de tourner sur l'ancien schéma jusqu'à ce qu'une requête réclame la
colonne manquante.
"""

from __future__ import annotations

from pathlib import Path

from sqlalchemy.engine import Engine

MIGRATIONS_DIR = Path(__file__).resolve().parents[1] / "migrations"


def apply_migrations(engine: Engine) -> None:
    """Applique toutes les migrations, dans l'ordre de leur numéro.

    Un appel par fichier, et non une concaténation : les migrations sont des
    lots distincts, et les fondre en une seule instruction masquerait laquelle a
    échoué.

    `exec_driver_sql` et non `text()` : ce dernier lit `:mot` comme un paramètre
    lié. Aucune migration n'en contient aujourd'hui, mais la première qui
    écrirait un « : » dans un littéral échouerait de façon illisible.

    Toutes les migrations doivent être rejouables : la fixture e2e les applique
    à chaque test sur un conteneur partagé.
    """
    paths = sorted(MIGRATIONS_DIR.glob("*.sql"))
    if not paths:
        raise RuntimeError(f"aucune migration trouvée dans {MIGRATIONS_DIR}")
    with engine.begin() as connection:
        for path in paths:
            connection.exec_driver_sql(path.read_text(encoding="utf-8"))
