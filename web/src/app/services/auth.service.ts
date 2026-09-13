import { HttpClient } from '@angular/common/http';
import { Injectable } from '@angular/core';
import { Observable } from 'rxjs';

import { API_BASE_URL } from '../api-config';
import { SessionInfo } from '../models/auth.model';

@Injectable({ providedIn: 'root' })
export class AuthService {
  constructor(private readonly http: HttpClient) {}

  /**
   * Valide un couple identifiant / mot de passe auprès de l'API.
   * 200 → identifiants bons ; 401 → mauvais ; 0 → API injoignable.
   */
  verify(actorId: string, bearerToken: string): Observable<SessionInfo> {
    return this.http.get<SessionInfo>(`${API_BASE_URL}/api/v1/auth/session`, {
      headers: { Authorization: `Bearer ${bearerToken}`, 'X-Actor-Id': actorId },
    });
  }
}
