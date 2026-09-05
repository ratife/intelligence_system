import { HttpErrorResponse, HttpEventType } from '@angular/common/http';
import { Component, OnDestroy, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { ImportProgress } from '../import-progress/import-progress';
import { FaceEvent } from '../models/event.model';
import { ImportItem, createImportItem, isTerminalStatus } from '../models/import-progress.model';
import { AuthCredentialsService } from '../services/auth-credentials.service';
import { EventImportService } from '../services/event-import.service';

type Mode = 'new' | 'existing';

@Component({
  selector: 'app-event-import',
  imports: [FormsModule, ImportProgress],
  templateUrl: './event-import.html',
  styleUrl: './event-import.css',
})
export class EventImport implements OnDestroy {
  mode: Mode = 'new';

  newDescription = '';
  newEventDate = '';
  newAddress = '';

  readonly events = signal<FaceEvent[]>([]);
  selectedEventId: number | null = null;

  readonly selectedFiles = signal<File[]>([]);

  readonly error = signal<string | null>(null);
  readonly resultEventId = signal<number | null>(null);

  /** File d'import : une entrée par image, mise à jour au fil des réponses. */
  readonly items = signal<ImportItem[]>([]);
  readonly running = signal(false);
  readonly startedAt = signal<number | null>(null);
  readonly finishedAt = signal<number | null>(null);

  private cancelling = false;
  private inFlight: Subscription | null = null;

  constructor(
    private readonly eventImportService: EventImportService,
    private readonly credentials: AuthCredentialsService,
  ) {}

  ngOnDestroy(): void {
    this.inFlight?.unsubscribe();
  }

  selectMode(mode: Mode): void {
    this.mode = mode;
    if (mode === 'existing' && this.events().length === 0) {
      this.refreshEvents();
    }
  }

  refreshEvents(): void {
    this.eventImportService
      .listEvents(this.credentials.actorId, this.credentials.bearerToken)
      .subscribe({
        next: (events) => this.events.set(events),
        error: (err: HttpErrorResponse) => this.error.set(this.describeError(err)),
      });
  }

  onFilesSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    this.selectedFiles.set(input.files ? Array.from(input.files) : []);
  }

  onSubmit(): void {
    const files = this.selectedFiles();
    if (files.length === 0) {
      this.error.set('Sélectionnez au moins une image.');
      return;
    }
    if (this.mode === 'existing' && this.selectedEventId === null) {
      this.error.set('Choisissez un événement existant.');
      return;
    }

    this.error.set(null);
    this.cancelling = false;
    this.items.set(files.map(createImportItem));
    this.startedAt.set(Date.now());
    this.finishedAt.set(null);
    this.resultEventId.set(null);
    this.running.set(true);

    if (this.mode === 'existing') {
      this.startQueue(this.selectedEventId as number);
      return;
    }

    this.inFlight = this.eventImportService
      .createEvent(this.credentials.actorId, this.credentials.bearerToken, {
        description: this.newDescription,
        event_date: this.newEventDate,
        address: this.newAddress,
      })
      .subscribe({
        next: (event) => {
          this.events.update((events) => [event, ...events]);
          this.startQueue(event.id);
        },
        // L'événement n'a pas pu être créé : la file n'a jamais démarré, donc
        // aucun avancement à montrer — seul le message d'erreur reste pertinent.
        error: (err: HttpErrorResponse) => {
          this.error.set(this.describeError(err));
          this.items.set([]);
          this.startedAt.set(null);
          this.finishRun();
        },
      });
  }

  /**
   * Interrompt la file. La requête en vol est abandonnée côté client ; le
   * serveur, lui, termine l'indexation de cette image (l'import y est
   * synchrone) — d'où le statut « annulée » plutôt qu'un retour arrière.
   */
  cancelRun(): void {
    if (!this.running()) {
      return;
    }
    this.cancelling = true;
    this.inFlight?.unsubscribe();
    this.inFlight = null;
    this.markRemainingCancelled();
    this.finishRun();
  }

  private startQueue(eventId: number): void {
    this.resultEventId.set(eventId);
    this.processNext(eventId, 0);
  }

  /**
   * Traite les images une par une, séquentiellement : c'est ce qui produit
   * l'avancement image par image, et cela évite de saturer les modèles ONNX
   * (chargés une seule fois côté API) avec des requêtes concurrentes.
   */
  private processNext(eventId: number, index: number): void {
    const files = this.selectedFiles();
    if (this.cancelling || index >= files.length) {
      this.finishRun();
      return;
    }

    const startedMs = Date.now();
    this.patchItem(index, { status: 'uploading', uploadedRatio: 0 });

    this.inFlight = this.eventImportService
      .uploadImage(this.credentials.actorId, this.credentials.bearerToken, eventId, files[index])
      .subscribe({
        next: (event) => {
          if (event.type === HttpEventType.UploadProgress) {
            const ratio = event.total ? Math.min(1, event.loaded / event.total) : 0;
            this.patchItem(
              index,
              ratio >= 1
                ? { status: 'indexing', uploadedRatio: 1 }
                : { status: 'uploading', uploadedRatio: ratio },
            );
          } else if (event.type === HttpEventType.Response) {
            const result = event.body?.results[0] ?? null;
            this.patchItem(
              index,
              result === null
                ? {
                    status: 'error',
                    error: "L'API n'a renvoyé aucun résultat pour cette image.",
                    durationMs: Date.now() - startedMs,
                  }
                : {
                    status: result.duplicate ? 'duplicate' : 'indexed',
                    uploadedRatio: 1,
                    imageId: result.image_id,
                    facesAccepted: result.faces_accepted,
                    facesRejected: result.faces_rejected,
                    durationMs: Date.now() - startedMs,
                  },
            );
          }
        },
        // Une image en échec n'interrompt pas le lot : elle est tracée et la file continue.
        error: (err: HttpErrorResponse) => {
          this.patchItem(index, {
            status: 'error',
            error: this.describeError(err),
            durationMs: Date.now() - startedMs,
          });
          this.processNext(eventId, index + 1);
        },
        complete: () => this.processNext(eventId, index + 1),
      });
  }

  private patchItem(index: number, patch: Partial<ImportItem>): void {
    this.items.update((items) =>
      items.map((item, position) => (position === index ? { ...item, ...patch } : item)),
    );
  }

  private markRemainingCancelled(): void {
    this.items.update((items) =>
      items.map((item) =>
        isTerminalStatus(item.status) ? item : { ...item, status: 'cancelled' },
      ),
    );
  }

  private finishRun(): void {
    this.inFlight = null;
    if (!this.running()) {
      return;
    }
    this.finishedAt.set(Date.now());
    this.running.set(false);
  }

  private describeError(err: HttpErrorResponse): string {
    const detail = (err.error as { detail?: string } | null)?.detail;
    if (detail) {
      return detail;
    }
    if (err.status === 0) {
      return (
        "Impossible de joindre l'API — vérifiez qu'elle tourne sur " + 'http://localhost:8000.'
      );
    }
    return `Erreur inattendue (HTTP ${err.status}).`;
  }
}
