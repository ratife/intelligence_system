import { HttpErrorResponse, HttpEventType } from '@angular/common/http';
import { Component, OnDestroy, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { ImportProgress } from '../import-progress/import-progress';
import { FaceEvent } from '../models/event.model';
import { ImportItem, createImportItem, isTerminalStatus } from '../models/import-progress.model';
import { SelectedPhoto, addPhotos, formatFileSize, totalSizeBytes } from '../photo-selection';
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

  /** Sélection cumulative : chaque passage par le sélecteur ajoute, ne remplace pas. */
  readonly photos = signal<SelectedPhoto[]>([]);
  readonly ignoredDuplicates = signal(0);

  readonly error = signal<string | null>(null);
  readonly resultEventId = signal<number | null>(null);

  /** File d'import : une entrée par image, mise à jour au fil des réponses. */
  readonly items = signal<ImportItem[]>([]);
  readonly running = signal(false);
  readonly startedAt = signal<number | null>(null);
  readonly finishedAt = signal<number | null>(null);

  private cancelling = false;
  private inFlight: Subscription | null = null;
  /** Photos figées au lancement : la file ne doit pas suivre une sélection modifiée. */
  private queuedFiles: File[] = [];

  constructor(
    private readonly eventImportService: EventImportService,
    private readonly credentials: AuthCredentialsService,
  ) {}

  ngOnDestroy(): void {
    this.inFlight?.unsubscribe();
  }

  readonly totalSizeLabel = computed(() => formatFileSize(totalSizeBytes(this.photos())));

  readonly oversizedCount = computed(() => this.photos().filter((photo) => photo.tooLarge).length);

  /**
   * Un fichier trop volumineux est un échec certain (413) : mieux vaut le
   * retirer d'un clic que de le découvrir après plusieurs minutes de file.
   */
  readonly canSubmit = computed(
    () => !this.running() && this.photos().length > 0 && this.oversizedCount() === 0,
  );

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
    const picked = input.files ? Array.from(input.files) : [];
    const result = addPhotos(this.photos(), picked);

    this.photos.set(result.photos);
    this.ignoredDuplicates.set(result.ignoredDuplicates);
    this.error.set(null);

    // Sans cette remise à zéro, resélectionner un fichier qu'on vient de retirer
    // ne déclencherait aucun `change` : la valeur de l'input n'aurait pas changé.
    input.value = '';
  }

  removePhoto(key: string): void {
    this.photos.update((photos) => photos.filter((photo) => photo.key !== key));
    this.ignoredDuplicates.set(0);
  }

  clearPhotos(): void {
    this.photos.set([]);
    this.ignoredDuplicates.set(0);
  }

  formatSize(bytes: number): string {
    return formatFileSize(bytes);
  }

  onSubmit(): void {
    const photos = this.photos();
    if (photos.length === 0) {
      this.error.set('Ajoutez au moins une photo.');
      return;
    }
    if (this.mode === 'existing' && this.selectedEventId === null) {
      this.error.set('Choisissez un événement existant.');
      return;
    }
    // Sans cette garde, un formulaire à moitié rempli crée un événement sans
    // description ni date — l'API les accepte vides, et il reste ensuite dans
    // le catalogue sans que rien ne permette de l'identifier.
    if (this.mode === 'new' && !this.hasCompleteEventFields()) {
      this.error.set("Renseignez la description, la date et l'adresse du nouvel événement.");
      return;
    }

    this.error.set(null);
    this.cancelling = false;
    this.queuedFiles = photos.map((photo) => photo.file);
    this.items.set(this.queuedFiles.map(createImportItem));
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
        description: this.newDescription.trim(),
        event_date: this.newEventDate,
        address: this.newAddress.trim(),
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

  private hasCompleteEventFields(): boolean {
    return (
      this.newDescription.trim().length > 0 &&
      this.newEventDate.length > 0 &&
      this.newAddress.trim().length > 0
    );
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
    if (this.cancelling || index >= this.queuedFiles.length) {
      this.finishRun();
      return;
    }

    const startedMs = Date.now();
    this.patchItem(index, { status: 'uploading', uploadedRatio: 0 });

    this.inFlight = this.eventImportService
      .uploadImage(
        this.credentials.actorId,
        this.credentials.bearerToken,
        eventId,
        this.queuedFiles[index],
      )
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
