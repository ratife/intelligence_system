"""Use case du pipeline de recherche : passage du visage soumis aux événements retrouvés.

Séquence (§7.1) : extraction requête (désambiguïsation explicite) → recherche
ANN top-K → seuillage → agrégation par événement → restitution avec preuve.
Réutilise le même détecteur/embedder que l'indexation (port partagé) pour
éviter toute divergence de pré-traitement (§5, « piège classique n°1 »).
"""

from __future__ import annotations

import hashlib

from facereco.application.dto import SearchByFaceCommand
from facereco.domain.entities.search import (
    FaceCandidate,
    FaceEvidence,
    SearchQueryInfo,
    SearchResult,
)
from facereco.domain.exceptions import (
    AmbiguousFaceSelectionError,
    InvalidFaceIndexError,
    NoFaceDetectedError,
    SearchQuotaExceededError,
)
from facereco.domain.ports.audit_log import AuditLogPort
from facereco.domain.ports.event_repository import EventRepositoryPort
from facereco.domain.ports.face_detector import FaceDetectorPort
from facereco.domain.ports.face_embedder import FaceEmbedderPort
from facereco.domain.ports.quota import SearchQuotaPort
from facereco.domain.ports.vector_search import VectorSearchHit, VectorSearchPort
from facereco.domain.services.event_scoring import aggregate_matches_by_event
from facereco.domain.value_objects.quality import DEFAULT_QUALITY_THRESHOLDS
from facereco.domain.value_objects.similarity import DEFAULT_SIMILARITY_THRESHOLD

DEFAULT_ANN_TOP_K = 200


class SearchByFaceUseCase:
    def __init__(
        self,
        face_detector: FaceDetectorPort,
        face_embedder: FaceEmbedderPort,
        vector_search: VectorSearchPort,
        event_repository: EventRepositoryPort,
        audit_log: AuditLogPort,
        quota: SearchQuotaPort,
        ann_top_k: int = DEFAULT_ANN_TOP_K,
    ) -> None:
        self._face_detector = face_detector
        self._face_embedder = face_embedder
        self._vector_search = vector_search
        self._event_repository = event_repository
        self._audit_log = audit_log
        self._quota = quota
        self._ann_top_k = ann_top_k

    def execute(self, command: SearchByFaceCommand) -> SearchResult:

        print(f"Executing search for actor {command.actor_id} with limit {command.limit}.")

        if not self._quota.check_and_consume(command.actor_id):
            raise SearchQuotaExceededError(command.actor_id)

        faces = self._face_detector.detect_faces(command.query_image_bytes)

        print(f"Detected {len(faces)} faces in the query image for actor {command.actor_id}.")
        
        if not faces:
            raise NoFaceDetectedError()

        selected_index = self._resolve_face_index(command.face_index, len(faces))
        selected_face = faces[selected_index]

        embedding = self._face_embedder.compute_embedding(command.query_image_bytes, selected_face)
        threshold_used = (
            command.threshold if command.threshold is not None else DEFAULT_SIMILARITY_THRESHOLD
        )
        model_version = self._face_embedder.model_version

        hits = self._vector_search.search_top_k(
            query=embedding,
            model_version=model_version,
            top_k=self._ann_top_k,
            min_quality_score=DEFAULT_QUALITY_THRESHOLDS.min_detection_score,
            date_from=command.date_from,
            date_to=command.date_to,
        )
        print(f"Found {len(hits)} hits in ANN search for actor {command.actor_id}.")
        qualifying_hits = [hit for hit in hits if hit.similarity >= threshold_used]

        events_by_id = self._event_repository.get_events_by_ids(
            list({hit.event_id for hit in qualifying_hits})
        )
        candidates = [
            FaceCandidate(
                event=events_by_id[hit.event_id],
                similarity=hit.similarity,
                evidence=_evidence_from_hit(hit),
            )
            for hit in qualifying_hits
            if hit.event_id in events_by_id
        ]

        matches = tuple(aggregate_matches_by_event(candidates)[: command.limit])

        query_hash = hashlib.sha256(command.query_image_bytes).hexdigest()
        self._audit_log.record_search(
            actor_id=command.actor_id,
            query_hash=query_hash,
            result_count=len(matches),
            top_score=matches[0].confidence if matches else None,
            threshold_used=threshold_used,
            model_version=model_version,
        )

        query_info = SearchQueryInfo(
            faces_detected=len(faces),
            face_used_index=selected_index,
            face_used_bbox=selected_face.bbox,
            face_used_quality=selected_face.detection_score,
            model_version=model_version,
        )
        return SearchResult(query_info=query_info, threshold_used=threshold_used, matches=matches)

    @staticmethod
    def _resolve_face_index(requested_index: int | None, faces_detected: int) -> int:
        if requested_index is None:
            if faces_detected > 1:
                raise AmbiguousFaceSelectionError(faces_detected)
            return 0
        if not 0 <= requested_index < faces_detected:
            raise InvalidFaceIndexError(requested_index, faces_detected)
        return requested_index


def _evidence_from_hit(hit: VectorSearchHit) -> FaceEvidence:
    return FaceEvidence(
        image_id=hit.image_id,
        storage_uri=hit.storage_uri,
        bbox=hit.bbox,
        similarity=hit.similarity,
    )
