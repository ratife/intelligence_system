import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-config';
import { TriggerIndexingResult } from '../models/indexing.model';

@Injectable({ providedIn: 'root' })
export class IndexingService {
  constructor(private readonly http: HttpClient) {}

  /**
   * Publie en file les images en attente d'indexation.
   *
   * L'appel **met en file**, il n'indexe pas : c'est le worker
   * (`make worker`, ou `make start` qui le lance aussi) qui consomme la file.
   * Relancer deux fois est sans risque — l'indexation est idempotente par
   * `(image_id, model_version, face_index)`, contrainte d'unicité en base.
   */
  trigger(actorId: string, bearerToken: string): Observable<TriggerIndexingResult> {
    return this.http.post<TriggerIndexingResult>(
      `${API_BASE_URL}/api/v1/admin/indexing/trigger`,
      null,
      { headers: { Authorization: `Bearer ${bearerToken}`, 'X-Actor-Id': actorId } },
    );
  }
}
