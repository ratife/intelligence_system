/**
 * Miroir TypeScript des schemas de `interface/api/schemas/events.py`
 * — GET /api/v1/events et GET /api/v1/events/{id}.
 *
 * À ne pas confondre avec `event.model.ts`, qui décrit les routes dev/démo
 * d'`admin_events` (création d'événement, import d'images).
 */

export interface EventSummary {
  id: number;
  title: string;
  description: string;
  event_date: string;
  address: string;
  image_count: number;
  indexed_image_count: number;
  pending_image_count: number;
  face_count: number;
  discarded_face_count: number;
  indexing_completion_rate: number;
  quality_rejection_rate: number;
  /** Faux quand aucun visage n'a été retenu : introuvable en recherche, même indexé. */
  is_searchable: boolean;
}

export interface EventListResponse {
  events: EventSummary[];
  total_count: number;
  offset: number;
  has_more: boolean;
}

export interface IndexedFace {
  face_index: number;
  /** `[x, y, largeur, hauteur]` en pixels de l'image décodée. */
  bbox: number[];
  detection_score: number;
  quality_score: number;
}

/** Un visage écarté par le filtre qualité. Sans cadre : `rejected_faces` ne stocke pas la bbox. */
export interface DiscardedFace {
  face_index: number;
  reason: string;
}

export interface EventImage {
  image_id: number;
  /** URL signée à courte durée de vie — valable le temps de consulter la page. */
  image_url: string;
  index_status: string;
  indexed_at: string | null;
  indexed_faces: IndexedFace[];
  discarded_faces: DiscardedFace[];
}

export interface EventDetail {
  event: EventSummary;
  images: EventImage[];
}
