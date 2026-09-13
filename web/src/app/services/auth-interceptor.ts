import { HttpErrorResponse, HttpInterceptorFn } from '@angular/common/http';
import { inject } from '@angular/core';
import { catchError, throwError } from 'rxjs';

import { AuthCredentialsService } from './auth-credentials.service';

/**
 * Reverrouille l'interface dès qu'une requête revient en 401.
 *
 * Sans cela, un jeton devenu invalide (rotation de `API_BEARER_TOKEN` côté
 * serveur) laisserait l'utilisateur « connecté » face à des écrans qui échouent
 * tous, sans moyen évident de ressaisir ses identifiants.
 *
 * L'erreur est propagée telle quelle : l'écran appelant reste libre d'afficher
 * son propre message.
 */
export const authInterceptor: HttpInterceptorFn = (request, next) => {
  const credentials = inject(AuthCredentialsService);
  return next(request).pipe(
    catchError((error: unknown) => {
      if (error instanceof HttpErrorResponse && error.status === 401 && credentials.unlocked()) {
        credentials.lock();
      }
      return throwError(() => error);
    }),
  );
};
