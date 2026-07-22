import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { EventMatch, SearchQueryInfo } from '../models/search.model';
import { SearchService } from '../services/search.service';

const ACTOR_ID_STORAGE_KEY = 'facereco.actorId';
const BEARER_TOKEN_STORAGE_KEY = 'facereco.bearerToken';

@Component({
  selector: 'app-search',
  imports: [FormsModule, DecimalPipe],
  templateUrl: './search.html',
  styleUrl: './search.css',
})
export class Search {
  actorId = localStorage.getItem(ACTOR_ID_STORAGE_KEY) ?? '';
  bearerToken = localStorage.getItem(BEARER_TOKEN_STORAGE_KEY) ?? '';

  faceIndex: number | null = null;
  threshold: number | null = null;
  dateFrom = '';
  dateTo = '';
  limit = 20;

  selectedFile: File | null = null;

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly hasSearched = signal(false);
  readonly queryInfo = signal<SearchQueryInfo | null>(null);
  readonly results = signal<EventMatch[]>([]);

  constructor(private readonly searchService: SearchService) {}

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFile = input.files?.[0] ?? null;
  }

  onSubmit(): void {
    if (!this.selectedFile) {
      this.error.set("Sélectionnez d'abord une photo.");
      return;
    }

    localStorage.setItem(ACTOR_ID_STORAGE_KEY, this.actorId);
    localStorage.setItem(BEARER_TOKEN_STORAGE_KEY, this.bearerToken);

    this.loading.set(true);
    this.error.set(null);

    this.searchService
      .searchByFace({
        actorId: this.actorId,
        bearerToken: this.bearerToken,
        image: this.selectedFile,
        faceIndex: this.faceIndex ?? undefined,
        threshold: this.threshold ?? undefined,
        dateFrom: this.dateFrom || undefined,
        dateTo: this.dateTo || undefined,
        limit: this.limit,
      })
      .subscribe({
        next: (response) => {
          this.queryInfo.set(response.query);
          this.results.set(response.results);
          this.hasSearched.set(true);
          this.loading.set(false);
        },
        error: (err: HttpErrorResponse) => {
          this.error.set(this.describeError(err));
          this.hasSearched.set(true);
          this.loading.set(false);
        },
      });
  }

  private describeError(err: HttpErrorResponse): string {
    const detail = (err.error as { detail?: string } | null)?.detail;
    if (detail) {
      return detail;
    }
    if (err.status === 0) {
      return "Impossible de joindre l'API — vérifiez qu'elle tourne sur " + 'http://localhost:8000.';
    }
    return `Erreur inattendue (HTTP ${err.status}).`;
  }
}
