import { HttpClient, HttpEvent } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-config';
import { CreateEventRequest, FaceEvent, ImportImagesResponse } from '../models/event.model';

function authHeaders(actorId: string, bearerToken: string): Record<string, string> {
  return { Authorization: `Bearer ${bearerToken}`, 'X-Actor-Id': actorId };
}

@Injectable({ providedIn: 'root' })
export class EventImportService {
  constructor(private readonly http: HttpClient) {}

  listEvents(actorId: string, bearerToken: string): Observable<FaceEvent[]> {
    return this.http.get<FaceEvent[]>(`${API_BASE_URL}/api/v1/admin/events`, {
      headers: authHeaders(actorId, bearerToken),
    });
  }

  createEvent(
    actorId: string,
    bearerToken: string,
    body: CreateEventRequest,
  ): Observable<FaceEvent> {
    return this.http.post<FaceEvent>(`${API_BASE_URL}/api/v1/admin/events`, body, {
      headers: authHeaders(actorId, bearerToken),
    });
  }

  /**
   * Envoie **une seule** image, en flux d'événements HTTP.
   *
   * La route accepte un lot, mais l'indexation y est synchrone : envoyer le lot
   * entier ne rendrait la main qu'à la fin, sans aucun avancement intermédiaire.
   * Une image par requête donne la granularité nécessaire à la barre de
   * progression, et `reportProgress` fournit en plus l'avancement de l'envoi
   * réseau avant que le serveur ne commence à indexer.
   */
  uploadImage(
    actorId: string,
    bearerToken: string,
    eventId: number,
    image: File,
  ): Observable<HttpEvent<ImportImagesResponse>> {
    const formData = new FormData();
    formData.append('images', image);
    return this.http.post<ImportImagesResponse>(
      `${API_BASE_URL}/api/v1/admin/events/${eventId}/images`,
      formData,
      {
        headers: authHeaders(actorId, bearerToken),
        reportProgress: true,
        observe: 'events',
      },
    );
  }
}
