import { HttpErrorResponse } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { AuthCredentialsService } from '../services/auth-credentials.service';
import { AuthService } from '../services/auth.service';

/**
 * Porte d'entrée de l'interface : rien n'est affiché tant que les identifiants
 * n'ont pas été validés par l'API (`GET /api/v1/auth/session`).
 *
 * Le « mot de passe » est le jeton bearer de l'API : il est donc vérifié côté
 * serveur, jamais comparé dans le navigateur.
 */
@Component({
  selector: 'app-login',
  imports: [FormsModule],
  templateUrl: './login.html',
  styleUrl: './login.css',
})
export class Login {
  actorId = '';
  password = '';

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);

  constructor(
    private readonly authService: AuthService,
    private readonly credentials: AuthCredentialsService,
  ) {}

  onSubmit(): void {
    const actorId = this.actorId.trim();
    if (!actorId || !this.password) {
      this.error.set('Renseignez votre identifiant et votre mot de passe.');
      return;
    }

    this.loading.set(true);
    this.error.set(null);

    this.authService.verify(actorId, this.password).subscribe({
      next: () => {
        // L'ordre compte : on vide le mot de passe du composant avant de
        // déverrouiller, pour ne pas le laisser traîner dans un champ détruit.
        const password = this.password;
        this.password = '';
        this.loading.set(false);
        this.credentials.unlock(actorId, password);
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(this.describeError(err));
        this.loading.set(false);
      },
    });
  }

  private describeError(err: HttpErrorResponse): string {
    if (err.status === 401) {
      return 'Identifiant ou mot de passe incorrect.';
    }
    if (err.status === 0) {
      return "Impossible de joindre l'API — vérifiez qu'elle tourne sur http://localhost:8000.";
    }
    return `Connexion impossible (HTTP ${err.status}).`;
  }
}
