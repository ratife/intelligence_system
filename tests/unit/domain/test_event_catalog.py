"""Les décisions de lecture du catalogue d'événements, testées sans base."""

from __future__ import annotations

from datetime import date

import pytest

from facereco.domain.entities.event import Event
from facereco.domain.value_objects.event_catalog import (
    EventCatalogPage,
    EventSummary,
)

EVENT = Event(
    id=7, description="Séminaire annuel", event_date=date(2026, 3, 14), address="Antananarivo"
)


def _summary(**overrides: int) -> EventSummary:
    counters: dict[str, int] = {
        "image_count": 10,
        "indexed_image_count": 10,
        "pending_image_count": 0,
        "face_count": 30,
        "discarded_face_count": 10,
    }
    counters.update(overrides)
    return EventSummary(event=EVENT, **counters)


def test_rejection_rate_is_over_detected_faces_not_images() -> None:
    """Même dénominateur qu'au tableau de bord : retenus + écartés.

    Rapporter les rejets aux images donnerait un « taux » sans signification
    (une image peut porter quinze visages), et deux écrans afficheraient deux
    nombres différents pour le même indicateur.
    """
    summary = _summary(face_count=30, discarded_face_count=10)

    assert summary.detected_face_count == 40
    assert summary.quality_rejection_rate == pytest.approx(0.25)


def test_indexing_completion_rate_is_over_all_images() -> None:
    assert _summary(image_count=8, indexed_image_count=2).indexing_completion_rate == 0.25


def test_rates_are_zero_when_nothing_to_measure() -> None:
    """Un événement vide s'affiche, il ne fait pas tomber l'écran."""
    empty = _summary(
        image_count=0,
        indexed_image_count=0,
        pending_image_count=0,
        face_count=0,
        discarded_face_count=0,
    )

    assert empty.indexing_completion_rate == 0.0
    assert empty.quality_rejection_rate == 0.0


def test_fully_indexed_event_without_retained_face_is_not_searchable() -> None:
    """Le diagnostic que la liste doit rendre visible.

    Un événement peut être indexé à 100 % et rester introuvable : si le filtre
    qualité a écarté tous ses visages, aucune recherche ne le fera ressortir.
    Un simple avancement d'indexation le présenterait comme terminé, sans dire
    qu'il ne sert à rien.
    """
    summary = _summary(image_count=4, indexed_image_count=4, face_count=0, discarded_face_count=9)

    assert summary.indexing_completion_rate == 1.0
    assert summary.is_searchable is False


def test_indexed_count_larger_than_total_is_rejected() -> None:
    """Signale une requête d'agrégation fausse au lieu d'afficher plus de 100 %."""
    with pytest.raises(ValueError, match="dépasse"):
        _summary(image_count=3, indexed_image_count=4)


def test_negative_counter_is_rejected() -> None:
    with pytest.raises(ValueError, match="face_count"):
        _summary(face_count=-1)


def test_page_knows_whether_more_events_remain() -> None:
    assert EventCatalogPage(events=(_summary(),), total_count=3).has_more is True
    assert EventCatalogPage(events=(_summary(),), total_count=1).has_more is False


def test_last_page_does_not_claim_more_because_it_is_short() -> None:
    """Une tranche plus petite que l'ensemble n'est pas une tranche incomplète.

    Sans l'offset, la dernière page (1 événement sur 3) se déclarerait suivie
    d'autres, et l'interface proposerait indéfiniment « charger la suite ».
    """
    last = EventCatalogPage(events=(_summary(),), total_count=3, offset=2)

    assert last.has_more is False


def test_page_cannot_extend_past_its_total() -> None:
    with pytest.raises(ValueError, match="dépassent"):
        EventCatalogPage(events=(_summary(), _summary()), total_count=1)

    with pytest.raises(ValueError, match="dépassent"):
        EventCatalogPage(events=(_summary(),), total_count=3, offset=3)
