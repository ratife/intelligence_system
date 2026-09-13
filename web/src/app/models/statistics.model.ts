/**
 * Miroir TypeScript des schemas de `interface/api/schemas/statistics.py`.
 * Pas de codegen : à mettre à jour en même temps que le schéma Pydantic.
 *
 * Les `*_rate` sont des fractions 0 → 1, calculées côté serveur (les
 * dénominateurs y portent des choix documentés, cf. `system_statistics.py`).
 */

export interface RejectionReason {
  reason: string;
  count: number;
}

export interface SystemStatistics {
  event_count: number;
  image_count: number;
  indexed_image_count: number;
  pending_image_count: number;
  face_count: number;
  rejected_face_count: number;
  detected_face_count: number;
  search_count: number;
  empty_search_count: number;
  distinct_actor_count: number;
  average_top_score: number | null;
  indexing_completion_rate: number;
  quality_rejection_rate: number;
  average_faces_per_indexed_image: number;
  empty_search_rate: number;
  rejections_by_reason: RejectionReason[];
  model_versions: string[];
}
