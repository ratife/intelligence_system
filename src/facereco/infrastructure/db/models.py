"""Modèles ORM SQLAlchemy — mapping base de données, distinct des entités du Domain.

`EventModel` représente le schéma existant du client (non modifié, cf. §2.1) ;
il n'est fourni ici que pour permettre au projet de tourner de façon autonome
en développement. Les autres tables sont celles introduites par le cadrage
technique (§8).
"""

from __future__ import annotations

import datetime as dt

from pgvector.sqlalchemy import Vector
from sqlalchemy import (
    ARRAY,
    REAL,
    BigInteger,
    Date,
    DateTime,
    ForeignKey,
    Integer,
    SmallInteger,
    String,
    Text,
)
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    pass


class EventModel(Base):
    """Schéma existant du client (rappel, §2.1), à une colonne près.

    `title` est la seule addition de ce service : la `description` d'origine
    servait d'intitulé faute de mieux (migration `0002`). Si ce stack venait à
    pointer vers la vraie table du client plutôt que vers la base de démo, c'est
    le point à renégocier — on ne modifie pas le schéma d'un système qu'on ne
    possède pas.
    """

    __tablename__ = "events"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    title: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str] = mapped_column(Text, nullable=False)
    event_date: Mapped[dt.date] = mapped_column(Date, nullable=False)
    address: Mapped[str] = mapped_column(Text, nullable=False)


class EventImageModel(Base):
    __tablename__ = "event_images"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    storage_uri: Mapped[str] = mapped_column(Text, nullable=False)
    content_hash: Mapped[str] = mapped_column(String(64), nullable=False, unique=True)
    width: Mapped[int | None] = mapped_column(Integer)
    height: Mapped[int | None] = mapped_column(Integer)
    indexed_at: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))
    index_status: Mapped[str] = mapped_column(Text, nullable=False, default="pending")


class FaceEmbeddingModel(Base):
    __tablename__ = "face_embeddings"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event_images.id", ondelete="CASCADE"), nullable=False
    )
    event_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("events.id", ondelete="CASCADE"), nullable=False
    )
    face_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    bbox: Mapped[list[int]] = mapped_column(ARRAY(Integer), nullable=False)
    det_score: Mapped[float] = mapped_column(REAL, nullable=False)
    quality_score: Mapped[float] = mapped_column(REAL, nullable=False)
    embedding: Mapped[list[float]] = mapped_column(Vector(512), nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    cluster_id: Mapped[int | None] = mapped_column(BigInteger, ForeignKey("person_clusters.id"))
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class RejectedFaceModel(Base):
    """Extension au schéma du document (§6.1) : les rejets qualité ne sont jamais silencieux."""

    __tablename__ = "rejected_faces"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    image_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("event_images.id", ondelete="CASCADE"), nullable=False
    )
    face_index: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    rejection_reason: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)


class PersonClusterModel(Base):
    __tablename__ = "person_clusters"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    centroid: Mapped[list[float]] = mapped_column(Vector(512), nullable=False)
    face_count: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    consent_state: Mapped[str] = mapped_column(Text, nullable=False, default="unknown")
    purge_after: Mapped[dt.datetime | None] = mapped_column(DateTime(timezone=True))


class SearchAuditLogModel(Base):
    __tablename__ = "search_audit_log"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    actor_id: Mapped[str] = mapped_column(Text, nullable=False)
    query_hash: Mapped[str] = mapped_column(String(64), nullable=False)
    result_count: Mapped[int] = mapped_column(Integer, nullable=False)
    top_score: Mapped[float | None] = mapped_column(REAL)
    threshold_used: Mapped[float] = mapped_column(REAL, nullable=False)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), nullable=False)
