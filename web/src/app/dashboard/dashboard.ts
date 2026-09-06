import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, computed, signal } from '@angular/core';

import { SystemStatistics } from '../models/statistics.model';
import { QueueStatus } from '../models/workers.model';
import { AuthCredentialsService } from '../services/auth-credentials.service';
import { IndexingService } from '../services/indexing.service';
import { StatisticsService } from '../services/statistics.service';
import { WorkersService } from '../services/workers.service';

/** Cadence de rafraîchissement pendant qu'une indexation est en cours. */
const POLL_INTERVAL_MS = 2000;

/**
 * Délai de repli avant de suspecter un worker absent.
 *
 * La file elle-même répond à la question (`is_stalled`), et bien plus vite. Ce
 * délai ne sert que si la supervision de file est indisponible.
 */
const NO_PROGRESS_WARNING_MS = 15000;

/**
 * Tableau de bord : volumétrie indexée, qualité de détection, activité de
 * recherche.
 *
 * C'est un modèle de lecture, pas de l'observabilité (Lot 3 : métriques,
 * traces, alertes) — délibérément hors périmètre. Les chiffres sont pris à la
 * demande, il n'y a ni historique ni série temporelle.
 */
@Component({
  selector: 'app-dashboard',
  templateUrl: './dashboard.html',
  styleUrl: './dashboard.css',
})
export class Dashboard implements OnDestroy {
  readonly stats = signal<SystemStatistics | null>(null);
  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly loadedAt = signal<Date | null>(null);

  /** Indexation : mise en file, puis suivi de la file qui se vide. */
  readonly triggering = signal(false);
  readonly queuedCount = signal<number | null>(null);
  readonly watching = signal(false);
  readonly workerSuspected = signal(false);

  private pollId: ReturnType<typeof setInterval> | null = null;
  private pendingAtTrigger = 0;
  private watchStartedMs = 0;

  /** État de la file d'indexation et de ses consommateurs. */
  readonly queue = signal<QueueStatus | null>(null);

  constructor(
    private readonly statisticsService: StatisticsService,
    private readonly indexingService: IndexingService,
    private readonly workersService: WorkersService,
    private readonly credentials: AuthCredentialsService,
  ) {
    this.refresh();
  }

  ngOnDestroy(): void {
    this.stopWatching();
  }

  /** Vrai quand rien n'a encore été indexé : on l'annonce plutôt qu'un mur de zéros. */
  readonly isEmpty = computed(() => {
    const stats = this.stats();
    return stats !== null && stats.image_count === 0 && stats.event_count === 0;
  });

  /** Plusieurs versions de modèle en base signalent une migration en cours. */
  readonly hasMixedModelVersions = computed(() => (this.stats()?.model_versions.length ?? 0) > 1);

  /** Segments part-à-tout des images. Un statut n'est jamais porté par la couleur seule. */
  readonly imageSegments = computed(() => {
    const stats = this.stats();
    if (stats === null) {
      return [];
    }
    // `image_count` peut dépasser indexées + en attente : les statuts `failed`
    // et `skipped` existent aussi (cf. IndexStatus). On expose le reste plutôt
    // que de le laisser disparaître silencieusement du total.
    const other = stats.image_count - stats.indexed_image_count - stats.pending_image_count;
    return [
      { label: 'Indexées', icon: '✓', tone: 'good', count: stats.indexed_image_count },
      { label: 'En attente', icon: '○', tone: 'accent', count: stats.pending_image_count },
      { label: 'Autre statut', icon: '⚠', tone: 'critical', count: Math.max(0, other) },
    ].filter((segment) => segment.count > 0);
  });

  /** Segments part-à-tout des visages détectés : retenus vs écartés par le filtre qualité. */
  readonly faceSegments = computed(() => {
    const stats = this.stats();
    if (stats === null) {
      return [];
    }
    return [
      { label: 'Retenus', icon: '✓', tone: 'good', count: stats.face_count },
      { label: 'Écartés', icon: '⚠', tone: 'warning', count: stats.rejected_face_count },
    ].filter((segment) => segment.count > 0);
  });

  /** Le plus gros motif de rejet, qui sert d'échelle aux barres. */
  readonly topRejectionCount = computed(() =>
    Math.max(1, ...(this.stats()?.rejections_by_reason ?? []).map((item) => item.count)),
  );

  /**
   * Met en file les images en attente, puis suit leur consommation.
   *
   * L'appel ne fait que publier : c'est le worker qui indexe. On surveille donc
   * la décrue du compteur plutôt que d'annoncer un travail fait, et on alerte
   * si rien ne bouge — cas typique du worker non démarré.
   */
  startIndexing(): void {
    this.triggering.set(true);
    this.error.set(null);
    this.workerSuspected.set(false);
    this.queuedCount.set(null);
    this.pendingAtTrigger = this.stats()?.pending_image_count ?? 0;

    this.indexingService.trigger(this.credentials.actorId, this.credentials.bearerToken).subscribe({
      next: (result) => {
        this.queuedCount.set(result.images_published);
        this.triggering.set(false);
        if (result.images_published > 0) {
          this.startWatching();
        }
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(this.describeError(err));
        this.triggering.set(false);
      },
    });
  }

  stopWatching(): void {
    if (this.pollId !== null) {
      clearInterval(this.pollId);
      this.pollId = null;
    }
    this.watching.set(false);
  }

  private startWatching(): void {
    this.stopWatching();
    this.watching.set(true);
    this.watchStartedMs = Date.now();
    this.pollId = setInterval(() => this.pollOnce(), POLL_INTERVAL_MS);
  }

  /** L'échec du chargement de la file n'empêche pas d'afficher les statistiques. */
  private loadQueue(): void {
    this.workersService.load(this.credentials.actorId, this.credentials.bearerToken).subscribe({
      next: (queue) => this.queue.set(queue),
      error: () => this.queue.set(null),
    });
  }

  private pollOnce(): void {
    this.loadQueue();
    this.statisticsService.load(this.credentials.actorId, this.credentials.bearerToken).subscribe({
      next: (stats) => {
        this.stats.set(stats);
        this.loadedAt.set(new Date());

        if (stats.pending_image_count === 0) {
          this.stopWatching();
          return;
        }
        // La supervision de file tranche directement : du retard et aucun
        // consommateur actif, c'est un worker à démarrer, pas une lenteur.
        if (this.queue()?.is_stalled === true) {
          this.workerSuspected.set(true);
          this.stopWatching();
          return;
        }
        // Repli si la supervision est indisponible : rien consommé passé le délai.
        const stalled = stats.pending_image_count >= this.pendingAtTrigger;
        if (stalled && Date.now() - this.watchStartedMs > NO_PROGRESS_WARNING_MS) {
          this.workerSuspected.set(true);
          this.stopWatching();
        }
      },
      // Un sondage raté n'interrompt pas le suivi : le prochain retentera.
      error: () => undefined,
    });
  }

  refresh(): void {
    this.loading.set(true);
    this.error.set(null);
    this.loadQueue();

    this.statisticsService.load(this.credentials.actorId, this.credentials.bearerToken).subscribe({
      next: (stats) => {
        this.stats.set(stats);
        this.loadedAt.set(new Date());
        this.loading.set(false);
      },
      error: (err: HttpErrorResponse) => {
        this.error.set(this.describeError(err));
        this.loading.set(false);
      },
    });
  }

  percent(rate: number): number {
    return Math.round(rate * 100);
  }

  /**
   * Motifs de rejet : `taille_visage<40px` → « Taille visage < 40px ».
   *
   * Transformation générique (souligné → espace, opérateur aéré) plutôt qu'une
   * table de correspondance : les motifs sont construits côté domaine avec le
   * seuil franchi (`quality.py`), une table se désynchroniserait en silence au
   * moindre changement de seuil ou de critère.
   */
  humanizeReason(reason: string): string {
    const spaced = reason.replace(/_/g, ' ').replace(/([<>]=?)/g, ' $1 ');
    return (spaced.charAt(0).toUpperCase() + spaced.slice(1)).replace(/\s+/g, ' ').trim();
  }

  formatDecimal(value: number): string {
    return value.toFixed(2).replace('.', ',');
  }

  /** Durées d'inactivité : lisibles d'un coup d'œil, de la seconde à l'heure. */
  formatIdle(seconds: number): string {
    if (seconds < 60) {
      return `${Math.round(seconds)} s`;
    }
    if (seconds < 3600) {
      return `${Math.round(seconds / 60)} min`;
    }
    if (seconds < 86400) {
      return `${Math.round(seconds / 3600)} h`;
    }
    return `${Math.round(seconds / 86400)} j`;
  }

  formatTime(date: Date): string {
    return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' });
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
