/**
 * Miroir TypeScript des schemas de `src/facereco/interface/api/schemas/search.py`
 * — POST /api/v1/search/faces et POST /api/v1/search/by-face.
 */

/** Un visage détecté dans la photo requête. `bbox` = `[x, y, largeur, hauteur]` en pixels. */
export interface QueryFace {
  index: number;
  bbox: number[];
  quality: number;
}

/** Réponse de la détection préalable : aucune recherche n'a été lancée. */
export interface QueryFacesResponse {
  faces_detected: number;
  faces: QueryFace[];
}

export interface SearchQueryInfo {
  faces_detected: number;
  face_used: QueryFace;
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

/** Miroir de `DetectQueryFacesCommand` : l'image seule, sans filtre ni quota. */
export interface DetectFacesParams {
  actorId: string;
  bearerToken: string;
  image: File;
}
