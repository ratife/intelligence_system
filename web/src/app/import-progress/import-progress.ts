import { Component, OnDestroy, computed, effect, input, output, signal } from '@angular/core';

import { ImportItem, ImportItemStatus } from '../models/import-progress.model';

/** Ton visuel d'un statut — un statut n'est jamais porté par la couleur seule (icône + libellé). */
type StatusTone = 'pending' | 'active' | 'good' | 'warning' | 'muted' | 'critical';

/** Un segment de barre de répartition : jamais identifié par sa seule couleur. */
interface BreakdownSegment {
  readonly label: string;
  readonly icon: string;
  readonly tone: StatusTone;
  readonly count: number;
}

interface StatusMeta {
  readonly label: string;
  readonly icon: string;
  readonly tone: StatusTone;
}

const STATUS_META: Record<ImportItemStatus, StatusMeta> = {
  pending: { label: 'En attente', icon: '○', tone: 'pending' },
  uploading: { label: 'Envoi', icon: '↑', tone: 'active' },
  indexing: { label: 'Indexation', icon: '◍', tone: 'active' },
  indexed: { label: 'Indexée', icon: '✓', tone: 'good' },
  duplicate: { label: 'Doublon', icon: '⧉', tone: 'muted' },
  error: { label: 'Échec', icon: '✕', tone: 'critical' },
  cancelled: { label: 'Annulée', icon: '–', tone: 'muted' },
};

/** Nombre d'images terminées à partir duquel l'estimation du temps restant est affichée. */
const MIN_SAMPLES_FOR_ETA = 2;

/**
 * Visualisation de l'avancement d'un import : compteur d'ensemble, répartition
 * des issues, et détail image par image.
 *
 * Composant purement présentationnel — il dérive tout de la file `items`
 * fournie par le parent, qui reste seul à piloter les requêtes.
 */
@Component({
  selector: 'app-import-progress',
  templateUrl: './import-progress.html',
  styleUrl: './import-progress.css',
})
export class ImportProgress implements OnDestroy {
  readonly items = input.required<ImportItem[]>();
  readonly running = input(false);
  readonly startedAt = input<number | null>(null);
  readonly finishedAt = input<number | null>(null);
  readonly eventId = input<number | null>(null);

  readonly cancelRequested = output<void>();

  /** Horloge du chrono : signal, donc sa réécriture suffit à redéclencher le rendu en mode zoneless. */
  private readonly nowMs = signal(Date.now());
  private tickerId: ReturnType<typeof setInterval> | null = null;

  constructor() {
    effect(() => (this.running() ? this.startTicker() : this.stopTicker()));
  }

  ngOnDestroy(): void {
    this.stopTicker();
  }

  readonly total = computed(() => this.items().length);

  /**
   * Images réellement traitées. Les annulées en sont exclues à dessein :
   * les compter ferait afficher 100 % à une file interrompue en cours de route.
   */
  readonly processed = computed(() => this.indexed() + this.duplicates() + this.errors());

  readonly indexed = computed(() => this.countByStatus('indexed'));
  readonly duplicates = computed(() => this.countByStatus('duplicate'));
  readonly errors = computed(() => this.countByStatus('error'));
  readonly cancelled = computed(() => this.countByStatus('cancelled'));

  readonly facesAccepted = computed(() => this.sumBy((item) => item.facesAccepted));
  readonly facesRejected = computed(() => this.sumBy((item) => item.facesRejected));
  readonly facesDetected = computed(() => this.facesAccepted() + this.facesRejected());

  /** Part des visages détectés écartés par le filtre qualité — indicateur à surveiller (§6.1). */
  readonly rejectionRatePercent = computed(() => {
    const detected = this.facesDetected();
    return detected === 0 ? 0 : Math.round((this.facesRejected() / detected) * 100);
  });

  readonly percent = computed(() => {
    const total = this.total();
    return total === 0 ? 0 : Math.round((this.processed() / total) * 100);
  });

  /** Rang, dans la file, de l'image en cours de traitement (-1 s'il n'y en a pas). */
  private readonly currentIndex = computed(() =>
    this.items().findIndex((item) => item.status === 'uploading' || item.status === 'indexing'),
  );

  readonly current = computed(() => this.items()[this.currentIndex()] ?? null);

  readonly currentPosition = computed(() => this.currentIndex() + 1);

  readonly elapsedMs = computed(() => {
    const startedAt = this.startedAt();
    if (startedAt === null) {
      return 0;
    }
    return (this.finishedAt() ?? this.nowMs()) - startedAt;
  });

  /** Temps restant estimé, extrapolé de la durée moyenne des images déjà traitées. */
  readonly etaMs = computed(() => {
    if (!this.running()) {
      return null;
    }
    const durations = this.items()
      .map((item) => item.durationMs)
      .filter((duration): duration is number => duration !== null);
    if (durations.length < MIN_SAMPLES_FOR_ETA) {
      return null;
    }
    const remaining = this.total() - this.processed();
    if (remaining <= 0) {
      return null;
    }
    const averageMs = durations.reduce((sum, duration) => sum + duration, 0) / durations.length;
    return Math.round(averageMs * remaining);
  });

  /** Issues des images déjà traitées — part-à-tout, légende obligatoire. */
  readonly imageSegments = computed<BreakdownSegment[]>(() =>
    [
      { ...STATUS_META['indexed'], count: this.indexed() },
      { ...STATUS_META['duplicate'], count: this.duplicates() },
      { ...STATUS_META['error'], count: this.errors() },
      { ...STATUS_META['cancelled'], count: this.cancelled() },
    ].filter((segment) => segment.count > 0),
  );

  /** Visages détectés : retenus vs écartés par le filtre qualité. */
  readonly faceSegments = computed<BreakdownSegment[]>(() =>
    [
      { label: 'Retenus', icon: '✓', tone: 'good' as const, count: this.facesAccepted() },
      { label: 'Écartés', icon: '⚠', tone: 'warning' as const, count: this.facesRejected() },
    ].filter((segment) => segment.count > 0),
  );

  meta(status: ImportItemStatus): StatusMeta {
    return STATUS_META[status];
  }

  formatDuration(ms: number): string {
    if (ms < 60_000) {
      return `${(ms / 1000).toFixed(1).replace('.', ',')} s`;
    }
    const minutes = Math.floor(ms / 60_000);
    const seconds = Math.round((ms % 60_000) / 1000);
    return `${minutes} min ${seconds.toString().padStart(2, '0')} s`;
  }

  formatSize(bytes: number): string {
    const megabytes = bytes / (1024 * 1024);
    if (megabytes >= 1) {
      return `${megabytes.toFixed(1).replace('.', ',')} Mo`;
    }
    return `${Math.max(1, Math.round(bytes / 1024))} Ko`;
  }

  private countByStatus(status: ImportItemStatus): number {
    return this.items().filter((item) => item.status === status).length;
  }

  private sumBy(pick: (item: ImportItem) => number): number {
    return this.items().reduce((sum, item) => sum + pick(item), 0);
  }

  private startTicker(): void {
    if (this.tickerId !== null) {
      return;
    }
    this.tickerId = setInterval(() => this.nowMs.set(Date.now()), 500);
  }

  private stopTicker(): void {
    if (this.tickerId === null) {
      return;
    }
    clearInterval(this.tickerId);
    this.tickerId = null;
  }
}
