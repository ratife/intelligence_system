import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-config';
import { QueueStatus } from '../models/workers.model';

@Injectable({ providedIn: 'root' })
export class WorkersService {
  constructor(private readonly http: HttpClient) {}

  load(actorId: string, bearerToken: string): Observable<QueueStatus> {
    return this.http.get<QueueStatus>(`${API_BASE_URL}/api/v1/admin/workers`, {
      headers: { Authorization: `Bearer ${bearerToken}`, 'X-Actor-Id': actorId },
    });
  }
}
