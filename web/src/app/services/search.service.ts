import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-config';
import {
  DetectFacesParams,
  QueryFacesResponse,
  SearchParams,
  SearchResponse,
} from '../models/search.model';

@Injectable({ providedIn: 'root' })
export class SearchService {
  constructor(private readonly http: HttpClient) {}

  /**
   * Situe les visages de la photo, sans rien chercher.
   *
   * Sert à rendre `face_index` désignable à l'écran : c'est le même détecteur
   * que la recherche, donc les cadres affichés sont ceux qu'elle utilisera.
   */
  detectFaces(params: DetectFacesParams): Observable<QueryFacesResponse> {
    const formData = new FormData();
    formData.append('image', params.image);

    return this.http.post<QueryFacesResponse>(`${API_BASE_URL}/api/v1/search/faces`, formData, {
      headers: this.authHeaders(params.actorId, params.bearerToken),
    });
  }

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
      headers: this.authHeaders(params.actorId, params.bearerToken),
    });
  }

  private authHeaders(actorId: string, bearerToken: string): Record<string, string> {
    return {
      Authorization: `Bearer ${bearerToken}`,
      'X-Actor-Id': actorId,
    };
  }
}
