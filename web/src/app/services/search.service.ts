import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-config';
import { SearchParams, SearchResponse } from '../models/search.model';

@Injectable({ providedIn: 'root' })
export class SearchService {
  constructor(private readonly http: HttpClient) {}

  searchByFace(params: SearchParams): Observable<SearchResponse> {
    const formData = new FormData();
    formData.append('image', params.image);
    if (params.faceIndex !== undefined) {
      formData.append('face_index', String(params.faceIndex));
    }
    if (params.threshold !== undefined) {
      formData.append('threshold', String(params.threshold));
    }
    if (params.dateFrom) {
      formData.append('date_from', params.dateFrom);
    }
    if (params.dateTo) {
      formData.append('date_to', params.dateTo);
    }
    if (params.limit !== undefined) {
      formData.append('limit', String(params.limit));
    }

    return this.http.post<SearchResponse>(`${API_BASE_URL}/api/v1/search/by-face`, formData, {
      headers: {
        Authorization: `Bearer ${params.bearerToken}`,
        'X-Actor-Id': params.actorId,
      },
    });
  }
}
