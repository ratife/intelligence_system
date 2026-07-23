/**
 * Miroir TypeScript des schemas de `interface/api/routers/admin_events.py` —
 * routes dev/démo de création d'événement et d'import d'images.
 */

export interface FaceEvent {
  id: number;
  description: string;
  event_date: string;
  address: string;
}

export interface CreateEventRequest {
  description: string;
  event_date: string;
  address: string;
}

export interface ImportedImage {
  filename: string;
  image_id: number;
  duplicate: boolean;
  faces_accepted: number;
  faces_rejected: number;
}

export interface ImportImagesResponse {
  event_id: number;
  results: ImportedImage[];
}
