"""Les deux use cases de lecture du catalogue, avec un port en mémoire."""

from __future__ import annotations

from datetime import date

import pytest

from facereco.application.dto import GetEventDetailCommand, ListEventsCommand
from facereco.application.use_cases.get_event_detail import GetEventDetailUseCase
from facereco.application.use_cases.list_events import ListEventsUseCase
from facereco.domain.entities.event import Event
from facereco.domain.exceptions import EventNotFoundError
from facereco.domain.value_objects.event_catalog import EventDetail, EventSummary
from facereco.domain.value_objects.model_version import ModelVersion

from .fakes import ScriptedEventCatalog

MODEL = ModelVersion(value="arcface-r100-v1")
EVENT = Event(id=7, description="Séminaire", event_date=date(2026, 3, 14), address="Antananarivo")
SUMMARY = EventSummary(
    event=EVENT,
    image_count=1,
    indexed_image_count=1,
    pending_image_count=0,
    face_count=2,
    discarded_face_count=0,
)


def test_unknown_event_raises_rather_than_returning_an_empty_detail() -> None:
    """Un détail vide se confondrait avec un événement réellement sans image.

    L'exception est déjà traduite en 404 par `error_handlers.py`.
    """
    use_case = GetEventDetailUseCase(catalog=ScriptedEventCatalog(), current_model_version=MODEL)

    with pytest.raises(EventNotFoundError):
        use_case.execute(GetEventDetailCommand(event_id=404))


def test_detail_is_read_for_the_current_model_version() -> None:
    """« Indexé » n'a de sens que pour une version de modèle donnée.

    Sans ce cadrage, une migration de modèle ferait apparaître deux fois les
    visages d'une même image — donc deux fois les cadres à l'écran.
    """
    catalog = ScriptedEventCatalog(details={7: EventDetail(summary=SUMMARY, images=())})
    use_case = GetEventDetailUseCase(catalog=catalog, current_model_version=MODEL)

    use_case.execute(GetEventDetailCommand(event_id=7))

    assert catalog.model_versions_seen == ["arcface-r100-v1"]


def test_listing_passes_the_current_model_version_too() -> None:
    catalog = ScriptedEventCatalog()
    ListEventsUseCase(catalog=catalog, current_model_version=MODEL).execute(ListEventsCommand())

    assert catalog.model_versions_seen == ["arcface-r100-v1"]


@pytest.mark.parametrize("limit", [0, -1])
def test_unbounded_listing_is_refused(limit: int) -> None:
    """Une liste d'événements sans borne est une requête qui grossit en silence."""
    with pytest.raises(ValueError, match="limit"):
        ListEventsCommand(limit=limit)


def test_negative_offset_is_refused() -> None:
    with pytest.raises(ValueError, match="offset"):
        ListEventsCommand(offset=-1)
