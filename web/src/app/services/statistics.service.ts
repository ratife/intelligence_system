import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-config';
import { SystemStatistics } from '../models/statistics.model';

@Injectable({ providedIn: 'root' })
export class StatisticsService {
  constructor(private readonly http: HttpClient) {}

  load(actorId: string, bearerToken: string): Observable<SystemStatistics> {
    return this.http.get<SystemStatistics>(`${API_BASE_URL}/api/v1/stats`, {
      headers: { Authorization: `Bearer ${bearerToken}`, 'X-Actor-Id': actorId },
    });
  }
}
