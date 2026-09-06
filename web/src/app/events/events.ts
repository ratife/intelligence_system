import { HttpErrorResponse } from '@angular/common/http';
import { Component, signal } from '@angular/core';

import { EventDetailView } from '../event-detail/event-detail';
import { EventDetail, EventSummary } from '../models/event-catalog.model';
import { AuthCredentialsService } from '../services/auth-credentials.service';
import { EventCatalogService } from '../services/event-catalog.service';

/** Taille de tranche. La liste est paginée : elle grossit avec la base, pas l'écran. */
const PAGE_SIZE = 25;

/**
 * Onglet « Événements » : parcourir le catalogue, puis inspecter un événement.
 *
 * Comble ce que ni le tableau de bord ni la recherche ne couvraient : le premier
 * agrège tout le système en un chiffre, la seconde part d'une photo. Entre les
 * deux, rien ne permettait de répondre à « qu'a-t-on indexé pour cet
 * événement-là, et qu'a-t-on écarté ».
 *
 * Ce composant charge (liste et détail) ; `EventDetailView` affiche. Pas de
 * routeur dans cette application : la sélection est un signal, comme les onglets.
 */
@Component({
  selector: 'app-events',
  imports: [EventDetailView],
  templateUrl: './events.html',
  styleUrl: './events.css',
})
export class Events {
  readonly events = signal<EventSummary[]>([]);
  readonly totalCount = signal(0);
  readonly hasMore = signal(false);
  readonly loading = signal(false);
  readonly loadingMore = signal(false);
  readonly error = signal<string | null>(null);

  readonly detail = signal<EventDetail | null>(null);
  readonly detailLoading = signal(false);

  constructor(
    private readonly catalog: EventCatalogService,
    private readonly credentials: AuthCredentialsService,
  ) {
    this.refresh();
  }

  refresh(): void {
    this.loading.set(true);
    this.error.set(null);
    this.load(0, (loaded) => this.events.set(loaded));
  }

  loadMore(): void {
    this.loadingMore.set(true);
    this.load(this.events().length, (loaded) =>
      this.events.update((current) => [...current, ...loaded]),
    );
  }

  openEvent(eventId: number): void {
    this.detailLoading.set(true);
    this.error.set(null);
    this.catalog
      .getEventDetail(this.credentials.actorId, this.credentials.bearerToken, eventId)
      .subscribe({
        next: (detail) => {
          this.detail.set(detail);
          this.detailLoading.set(false);
        },
        error: (err: HttpErrorResponse) => {
          this.error.set(this.describeError(err));
          this.detailLoading.set(false);
        },
      });
  }

  closeDetail(): void {
    this.detail.set(null);
  }

  percent(rate: number): number {
    return Math.round(rate * 100);
  }

  /** Voir `EventDetailView.formatDate` : une date d'événement n'a pas de fuseau. */
  formatDate(isoDate: string): string {
    const [year, month, day] = isoDate.split('-');
    return day && month && year ? `${day}/${month}/${year}` : isoDate;
  }

  private load(offset: number, apply: (loaded: EventSummary[]) => void): void {
    this.catalog
      .listEvents(this.credentials.actorId, this.credentials.bearerToken, PAGE_SIZE, offset)
      .subscribe({
        next: (page) => {
          apply(page.events);
          this.totalCount.set(page.total_count);
          this.hasMore.set(page.has_more);
          this.loading.set(false);
          this.loadingMore.set(false);
        },
        error: (err: HttpErrorResponse) => {
          this.error.set(this.describeError(err));
          this.loading.set(false);
          this.loadingMore.set(false);
        },
      });
  }

  private describeError(err: HttpErrorResponse): string {
    const detail = (err.error as { detail?: string } | null)?.detail;
    if (detail) {
      return detail;
    }
    if (err.status === 0) {
      return "Impossible de joindre l'API — vérifiez qu'elle tourne sur http://localhost:8000.";
    }
    return `Erreur inattendue (HTTP ${err.status}).`;
  }
}
