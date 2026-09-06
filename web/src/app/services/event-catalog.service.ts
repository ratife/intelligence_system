import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-config';
import { EventDetail, EventListResponse } from '../models/event-catalog.model';

@Injectable({ providedIn: 'root' })
export class EventCatalogService {
  constructor(private readonly http: HttpClient) {}

  listEvents(
    actorId: string,
    bearerToken: string,
    limit: number,
    offset: number,
  ): Observable<EventListResponse> {
    return this.http.get<EventListResponse>(`${API_BASE_URL}/api/v1/events`, {
      headers: this.authHeaders(actorId, bearerToken),
      params: { limit, offset },
    });
  }

  getEventDetail(actorId: string, bearerToken: string, eventId: number): Observable<EventDetail> {
    return this.http.get<EventDetail>(`${API_BASE_URL}/api/v1/events/${eventId}`, {
      headers: this.authHeaders(actorId, bearerToken),
    });
  }

  private authHeaders(actorId: string, bearerToken: string): Record<string, string> {
    return { Authorization: `Bearer ${bearerToken}`, 'X-Actor-Id': actorId };
  }
}
