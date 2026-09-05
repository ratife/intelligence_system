import { Injectable, signal } from '@angular/core';

const ACTOR_ID_STORAGE_KEY = 'facereco.actorId';
const TOKEN_STORAGE_KEY = 'facereco.bearerToken';

/**
 * État de session de l'interface : identifiants MVP (acteur + jeton partagé) et
 * verrou d'accès aux écrans.
 *
 * Conservés en `sessionStorage` et non `localStorage` : la session se referme à
 * la fermeture du navigateur, ce qui est le sens même de l'écran de connexion.
 * Un rechargement de page (F5) reste, lui, transparent.
 *
 * Portée de la protection : le mot de passe saisi *est* le jeton bearer de
 * l'API, réellement vérifié côté serveur. Cet écran empêche l'accès fortuit à
 * l'interface ; il n'ajoute rien à la sécurité de l'API, déjà protégée par ce
 * même jeton, et le jeton reste lisible par tout script de la page.
 */
@Injectable({ providedIn: 'root' })
export class AuthCredentialsService {
  actorId = '';
  bearerToken = '';

  /**
   * Signal, et pas un champ simple : il est écrit depuis un `.subscribe()` et,
   * en mode zoneless, seule une écriture de signal redéclenche le rendu.
   */
  readonly unlocked = signal(false);

  constructor() {
    const actorId = this.read(ACTOR_ID_STORAGE_KEY);
    const bearerToken = this.read(TOKEN_STORAGE_KEY);
    if (actorId && bearerToken) {
      this.actorId = actorId;
      this.bearerToken = bearerToken;
      this.unlocked.set(true);
    }
  }

  /** Appelé une fois les identifiants validés par l'API. */
  unlock(actorId: string, bearerToken: string): void {
    this.actorId = actorId;
    this.bearerToken = bearerToken;
    this.write(ACTOR_ID_STORAGE_KEY, actorId);
    this.write(TOKEN_STORAGE_KEY, bearerToken);
    this.unlocked.set(true);
  }

  /** Déconnexion manuelle, ou rejet 401 constaté par l'intercepteur. */
  lock(): void {
    this.actorId = '';
    this.bearerToken = '';
    this.remove(ACTOR_ID_STORAGE_KEY);
    this.remove(TOKEN_STORAGE_KEY);
    this.unlocked.set(false);
  }

  // `sessionStorage` peut lever (navigation privée, stockage bloqué) : une
  // session non mémorisée est acceptable, une interface qui plante ne l'est pas.
  private read(key: string): string | null {
    try {
      return sessionStorage.getItem(key);
    } catch {
      return null;
    }
  }

  private write(key: string, value: string): void {
    try {
      sessionStorage.setItem(key, value);
    } catch {
      /* session non mémorisée : sans effet sur l'écran courant */
    }
  }

  private remove(key: string): void {
    try {
      sessionStorage.removeItem(key);
    } catch {
      /* rien à nettoyer */
    }
  }
}
