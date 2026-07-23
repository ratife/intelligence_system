import { HttpErrorResponse } from '@angular/common/http';
import { Component, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { FaceEvent, ImportedImage } from '../models/event.model';
import { AuthCredentialsService } from '../services/auth-credentials.service';
import { EventImportService } from '../services/event-import.service';

type Mode = 'new' | 'existing';

@Component({
  selector: 'app-event-import',
  imports: [FormsModule],
  templateUrl: './event-import.html',
  styleUrl: './event-import.css',
})
export class EventImport {
  mode: Mode = 'new';

  newDescription = '';
  newEventDate = '';
  newAddress = '';

  readonly events = signal<FaceEvent[]>([]);
  selectedEventId: number | null = null;

  selectedFiles: File[] = [];

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly resultEventId = signal<number | null>(null);
  readonly results = signal<ImportedImage[]>([]);

  constructor(
    private readonly eventImportService: EventImportService,
    readonly credentials: AuthCredentialsService,
  ) {}

  selectMode(mode: Mode): void {
    this.mode = mode;
    if (mode === 'existing' && this.events().length === 0) {
      this.refreshEvents();
    }
  }

  refreshEvents(): void {
    this.credentials.persist();
    this.eventImportService
      .listEvents(this.credentials.actorId, this.credentials.bearerToken)
      .subscribe({
        next: (events) => this.events.set(events),
        error: (err: HttpErrorResponse) => this.error.set(this.describeError(err)),
      });
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFiles = input.files ? Array.from(input.files) : [];
  }

  onSubmit(): void {
    if (this.selectedFiles.length === 0) {
      this.error.set("Sélectionnez au moins une image.");
      return;
    }
    if (this.mode === 'existing' && this.selectedEventId === null) {
      this.error.set('Choisissez un événement existant.');
      return;
    }

    this.credentials.persist();
    this.loading.set(true);
    this.error.set(null);

    if (this.mode === 'existing') {
      this.uploadTo(this.selectedEventId as number);
      return;
    }

    this.eventImportService
      .createEvent(this.credentials.actorId, this.credentials.bearerToken, {
        description: this.newDescription,
        event_date: this.newEventDate,
        address: this.newAddress,
      })
      .subscribe({
        next: (event) => {
          this.events.update((events) => [event, ...events]);
          this.uploadTo(event.id);
        },
        error: (err: HttpErrorResponse) => {
          this.error.set(this.describeError(err));
          this.loading.set(false);
        },
      });
  }

  private uploadTo(eventId: number): void {
    this.eventImportService
      .uploadImages(
        this.credentials.actorId,
        this.credentials.bearerToken,
        eventId,
        this.selectedFiles,
      )
      .subscribe({
        next: (response) => {
          this.resultEventId.set(response.event_id);
          this.results.set(response.results);
          this.loading.set(false);
        },
        error: (err: HttpErrorResponse) => {
          this.error.set(this.describeError(err));
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
