import { Injectable } from '@angular/core';

const ACTOR_ID_STORAGE_KEY = 'facereco.actorId';
const BEARER_TOKEN_STORAGE_KEY = 'facereco.bearerToken';

/** Identifiants MVP (jeton partagé + acteur) partagés entre tous les écrans, persistés en localStorage. */
@Injectable({ providedIn: 'root' })
export class AuthCredentialsService {
  actorId = localStorage.getItem(ACTOR_ID_STORAGE_KEY) ?? '';
  bearerToken = localStorage.getItem(BEARER_TOKEN_STORAGE_KEY) ?? '';

  persist(): void {
    localStorage.setItem(ACTOR_ID_STORAGE_KEY, this.actorId);
    localStorage.setItem(BEARER_TOKEN_STORAGE_KEY, this.bearerToken);
  }
}
