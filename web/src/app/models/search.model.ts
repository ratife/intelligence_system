/**
 * Miroir TypeScript de `SearchResponseSchema`
 * (src/facereco/interface/api/schemas/search.py) — POST /api/v1/search/by-face.
 */

export interface FaceUsed {
  index: number;
  bbox: number[];
  quality: number;
}

export interface SearchQueryInfo {
  faces_detected: number;
  face_used: FaceUsed;
  model_version: string;
}

export interface Evidence {
  image_id: number;
  image_url: string;
  bbox: number[];
  similarity: number;
}

export interface EventMatch {
  event_id: number;
  description: string;
  event_date: string;
  address: string;
  confidence: number;
  match_count: number;
  evidence: Evidence;
}

export interface SearchResponse {
  query: SearchQueryInfo;
  threshold_used: number;
  results: EventMatch[];
}

/** Paramètres du formulaire de recherche — miroir de `SearchByFaceCommand`. */
export interface SearchParams {
  actorId: string;
  bearerToken: string;
  image: File;
  faceIndex?: number;
  threshold?: number;
  dateFrom?: string;
  dateTo?: string;
  limit?: number;
}
