"""Implémentation PostgreSQL du port EventCatalogPort — projections du catalogue.

Deux points de conception dans les requêtes ci-dessous.

**Pas d'éventail de jointures.** Joindre `event_images`, `face_embeddings` et
`rejected_faces` dans une seule requête à plat produit un produit cartésien par
image (15 visages × 20 rejets = 300 lignes pour une seule photo). Les compteurs
passent donc par des sous-requêtes `LATERAL` corrélées, évaluées uniquement pour
les événements de la tranche demandée.

**Les rejets sont dédoublonnés sur `(image_id, face_index)`.** `rejected_faces`
n'a pas de contrainte d'unicité, et une image dont *tous* les visages sont
écartés reste éligible à l'indexation (`list_images_needing_indexing` la
resélectionne, faute d'empreinte pour la version de modèle courante) : chaque
relance y réinsère donc les mêmes rejets. Compter les lignes brutes afficherait
« 12 visages écartés » là où l'image en a un seul, écarté douze fois. Le
dédoublonnage est un correctif d'affichage, pas une réparation : la duplication
en base reste à traiter (contrainte d'unicité, ou changement de statut).
"""

from __future__ import annotations

from sqlalchemy import text
from sqlalchemy.orm import Session

from facereco.domain.entities.event import Event, EventImage, IndexStatus
from facereco.domain.ports.event_catalog import EventCatalogPort
from facereco.domain.value_objects.bounding_box import BoundingBox
from facereco.domain.value_objects.event_catalog import (
    DiscardedFace,
    EventCatalogPage,
    EventDetail,
    EventImageDetail,
    EventSummary,
    IndexedFace,
)
from facereco.domain.value_objects.model_version import ModelVersion

_LIST_SQL = text(
    """
    WITH page AS (
        SELECT id, description, event_date, address
        FROM events
        ORDER BY event_date DESC, id DESC
        LIMIT :limit OFFSET :offset
    )
    SELECT p.id, p.description, p.event_date, p.address,
           img.total AS image_count,
           img.done AS indexed_count,
           img.pending AS pending_count,
           fac.faces AS face_count,
           rej.discarded AS discarded_count
    FROM page p
    LEFT JOIN LATERAL (
        SELECT count(*) AS total,
               count(*) FILTER (WHERE index_status = 'done') AS done,
               count(*) FILTER (WHERE index_status = 'pending') AS pending
        FROM event_images WHERE event_id = p.id
    ) img ON true
    LEFT JOIN LATERAL (
        SELECT count(*) AS faces
        FROM face_embeddings
        WHERE event_id = p.id AND model_version = :model_version
    ) fac ON true
    LEFT JOIN LATERAL (
        SELECT count(DISTINCT (rf.image_id, rf.face_index)) AS discarded
        FROM rejected_faces rf
        JOIN event_images ei ON ei.id = rf.image_id
        WHERE ei.event_id = p.id
    ) rej ON true
    ORDER BY p.event_date DESC, p.id DESC
    """
)

_EVENT_SQL = text("SELECT id, description, event_date, address FROM events WHERE id = :event_id")

_IMAGES_SQL = text(
    """
    SELECT id, event_id, storage_uri, content_hash, width, height, index_status, indexed_at
    FROM event_images
    WHERE event_id = :event_id
    ORDER BY id
    """
)

_FACES_SQL = text(
    """
    SELECT image_id, face_index, bbox, det_score, quality_score
    FROM face_embeddings
    WHERE event_id = :event_id AND model_version = :model_version
    ORDER BY image_id, face_index
    """
)

# `DISTINCT ON` retient le rejet le plus ancien pour chaque visage : le motif
# d'origine, et non celui d'un rejeu ultérieur.
_DISCARDED_SQL = text(
    """
    SELECT DISTINCT ON (rf.image_id, rf.face_index)
           rf.image_id, rf.face_index, rf.rejection_reason
    FROM rejected_faces rf
    JOIN event_images ei ON ei.id = rf.image_id
    WHERE ei.event_id = :event_id
    ORDER BY rf.image_id, rf.face_index, rf.created_at
    """
)


class PostgresEventCatalog(EventCatalogPort):
    def __init__(self, session: Session) -> None:
        self._session = session

    def list_events(self, model_version: ModelVersion, limit: int, offset: int) -> EventCatalogPage:
        rows = self._session.execute(
            _LIST_SQL,
            {"model_version": str(model_version), "limit": limit, "offset": offset},
        ).all()
        total = self._session.execute(text("SELECT count(*) FROM events")).scalar() or 0

        return EventCatalogPage(
            events=tuple(
                EventSummary(
                    event=Event(
                        id=row.id,
                        description=row.description,
                        event_date=row.event_date,
                        address=row.address,
                    ),
                    image_count=row.image_count,
                    indexed_image_count=row.indexed_count,
                    pending_image_count=row.pending_count,
                    face_count=row.face_count,
                    discarded_face_count=row.discarded_count,
                )
                for row in rows
            ),
            total_count=total,
            offset=offset,
        )

    def get_event_detail(self, event_id: int, model_version: ModelVersion) -> EventDetail | None:
        event_row = self._session.execute(_EVENT_SQL, {"event_id": event_id}).one_or_none()
        if event_row is None:
            return None

        faces_by_image: dict[int, list[IndexedFace]] = {}
        for row in self._session.execute(
            _FACES_SQL, {"event_id": event_id, "model_version": str(model_version)}
        ):
            faces_by_image.setdefault(row.image_id, []).append(
                IndexedFace(
                    face_index=row.face_index,
                    bbox=BoundingBox(
                        x=row.bbox[0], y=row.bbox[1], width=row.bbox[2], height=row.bbox[3]
                    ),
                    detection_score=float(row.det_score),
                    quality_score=float(row.quality_score),
                )
            )

        discarded_by_image: dict[int, list[DiscardedFace]] = {}
        for row in self._session.execute(_DISCARDED_SQL, {"event_id": event_id}):
            discarded_by_image.setdefault(row.image_id, []).append(
                DiscardedFace(face_index=row.face_index, reason=row.rejection_reason)
            )

        images = tuple(
            EventImageDetail(
                image=EventImage(
                    id=row.id,
                    event_id=row.event_id,
                    storage_uri=row.storage_uri,
                    content_hash=row.content_hash,
                    width=row.width or 0,
                    height=row.height or 0,
                    index_status=IndexStatus(row.index_status),
                    indexed_at=row.indexed_at,
                ),
                indexed_faces=tuple(faces_by_image.get(row.id, ())),
                discarded_faces=tuple(discarded_by_image.get(row.id, ())),
            )
            for row in self._session.execute(_IMAGES_SQL, {"event_id": event_id})
        )

        return EventDetail(
            # Compteurs dérivés des listes affichées, et non d'une agrégation
            # séparée : un total qui contredirait le détail affiché juste en
            # dessous serait le pire des deux mondes.
            summary=EventSummary(
                event=Event(
                    id=event_row.id,
                    description=event_row.description,
                    event_date=event_row.event_date,
                    address=event_row.address,
                ),
                image_count=len(images),
                indexed_image_count=sum(
                    1 for detail in images if detail.image.index_status is IndexStatus.DONE
                ),
                pending_image_count=sum(
                    1 for detail in images if detail.image.index_status is IndexStatus.PENDING
                ),
                face_count=sum(len(detail.indexed_faces) for detail in images),
                discarded_face_count=sum(len(detail.discarded_faces) for detail in images),
            ),
            images=images,
        )
