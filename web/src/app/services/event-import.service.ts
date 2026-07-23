import { HttpClient } from '@angular/common/http';
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

  uploadImages(
    actorId: string,
    bearerToken: string,
    eventId: number,
    images: File[],
  ): Observable<ImportImagesResponse> {
    const formData = new FormData();
    for (const image of images) {
      formData.append('images', image);
    }
    return this.http.post<ImportImagesResponse>(
      `${API_BASE_URL}/api/v1/admin/events/${eventId}/images`,
      formData,
      { headers: authHeaders(actorId, bearerToken) },
    );
  }
}
