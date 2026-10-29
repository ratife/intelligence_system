import { DecimalPipe, DatePipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, ElementRef, OnDestroy, computed, signal, viewChild } from '@angular/core';
import { FormsModule } from '@angular/forms';
import { Subscription } from 'rxjs';

import { FaceCrop } from '../face-crop/face-crop';
import { FaceBox, FaceFrame } from '../face-frame/face-frame';
import { EventMatch, QueryFace } from '../models/search.model';
import { SearchResult } from '../search-result/search-result';
import { AuthCredentialsService } from '../services/auth-credentials.service';
import { SearchService } from '../services/search.service';

/**
 * Miroir indicatif de `search_quota_per_actor_per_minute` (`settings.py`). La
 * valeur réelle se règle côté serveur : celle-ci ne sert qu'à situer le compteur
 * affiché, l'API reste seule juge (429).
 */
const SEARCH_QUOTA_PER_MINUTE = 30;

/** Attente après un 429 : la fenêtre du quota est glissante sur une minute. */
const QUOTA_BACKOFF_MS = 60_000;

/** Flux pas encore prêt (`videoWidth` à 0) : on retente vite plutôt qu'un cycle entier. */
const NOT_READY_RETRY_MS = 500;

const JPEG_QUALITY = 0.9;

type CyclePhase = 'idle' | 'detecting' | 'searching' | 'waiting' | 'throttled' | 'hidden';

interface JournalEntry {
  eventId: number;
  /** Le meilleur hit vu pour cet événement : c'est sa preuve qui est montrée. */
  best: EventMatch;
  hits: number;
  lastSeen: Date;
}

/**
 * Recherche en continu sur le flux de la caméra du poste.
 *
 * Chaque cycle capture une image, la fait analyser par la détection (gratuite :
 * ni quota ni audit), et ne lance une recherche que s'il y a un visage. Trois
 * choix structurent l'écran :
 *
 * - **boucle séquentielle** : le cycle suivant part après la fin du précédent,
 *   jamais en parallèle. Le détecteur et l'embedder sont des instances uniques
 *   côté API, et des requêtes qui se chevauchent n'iraient pas plus vite ;
 * - **le plus grand visage du cadre** est cherché. Chercher chaque visage à
 *   chaque cycle épuiserait le quota dès deux personnes. Le choix est affiché,
 *   tous les visages restent encadrés : le système choisit, mais à découvert ;
 * - **les cadres sont posés sur l'image figée qui les a produits**, jamais sur
 *   la vidéo en direct, où ils seraient décalés d'un ou deux cycles.
 *
 * C'est de l'identification biométrique en temps réel : le Lot 0 (base légale,
 * AIPD) doit la couvrir explicitement avant toute utilisation sur données réelles.
 */
@Component({
  selector: 'app-camera-search',
  imports: [FormsModule, DecimalPipe, DatePipe, FaceFrame, FaceCrop, SearchResult],
  templateUrl: './camera-search.html',
  styleUrl: './camera-search.css',
})
export class CameraSearch implements OnDestroy {
  readonly quotaPerMinute = SEARCH_QUOTA_PER_MINUTE;
  readonly intervals = [2000, 3000, 5000];

  intervalMs = 3000;
  threshold: number | null = null;
  limit = 10;

  private readonly video = viewChild.required<ElementRef<HTMLVideoElement>>('video');

  readonly devices = signal<MediaDeviceInfo[]>([]);
  deviceId = '';

  readonly starting = signal(false);
  readonly running = signal(false);
  readonly cameraError = signal<string | null>(null);

  readonly phase = signal<CyclePhase>('idle');
  readonly cycleError = signal<string | null>(null);
  readonly resumeAt = signal<Date | null>(null);

  readonly frameUrl = signal<string | null>(null);
  readonly frameFaces = signal<QueryFace[]>([]);
  readonly usedFaceIndex = signal<number | null>(null);
  readonly results = signal<EventMatch[]>([]);
  /** Faux tant qu'aucun visage n'a été cherché : distingue « rien trouvé » de « rien cherché ». */
  readonly searchedThisCycle = signal(false);

  readonly journal = signal<JournalEntry[]>([]);
  private readonly searchTimes = signal<number[]>([]);
  readonly searchesLastMinute = computed(() => this.searchTimes().length);

  private stream: MediaStream | null = null;
  private timer: ReturnType<typeof setTimeout> | null = null;
  private inFlight: Subscription | null = null;
  /** Incrémenté à chaque annulation : un cycle suspendu sur la capture sait qu'il est périmé. */
  private generation = 0;
  private readonly canvas = document.createElement('canvas');

  private readonly onVisibilityChange = (): void => {
    if (!document.hidden && this.running() && this.phase() === 'hidden') {
      this.scheduleNext(0);
    }
  };

  constructor(
    private readonly searchService: SearchService,
    private readonly credentials: AuthCredentialsService,
  ) {
    document.addEventListener('visibilitychange', this.onVisibilityChange);
  }

  ngOnDestroy(): void {
    document.removeEventListener('visibilitychange', this.onVisibilityChange);
    this.stop();
    this.setFrame(null, []);
  }

  readonly frameBoxes = computed<FaceBox[]>(() => {
    const faces = this.frameFaces();
    const used = this.usedFaceIndex();
    return faces.map((face) => ({
      index: face.index,
      bbox: face.bbox,
      tone: face.index === used ? ('selected' as const) : ('other' as const),
      label: faces.length > 1 ? `#${face.index}` : '',
      title:
        face.index === used
          ? `Visage #${face.index} — le plus grand du cadre, recherché`
          : `Visage #${face.index} — non recherché`,
    }));
  });

  async start(): Promise<void> {
    this.cameraError.set(null);
    this.cycleError.set(null);

    // `navigator.mediaDevices` n'existe tout simplement pas hors contexte
    // sécurisé : sans ce test, l'écran échouerait sur un `undefined` muet.
    if (!window.isSecureContext || navigator.mediaDevices?.getUserMedia === undefined) {
      this.cameraError.set(
        "Le navigateur n'autorise la caméra que sur une page sécurisée : HTTPS, ou " +
          "localhost. Ouvrez l'interface depuis ce poste via http://localhost, ou servez-la en HTTPS.",
      );
      return;
    }

    this.starting.set(true);
    try {
      await this.openStream();
      this.running.set(true);
      this.scheduleNext(0);
    } catch (err) {
      this.cameraError.set(this.describeCameraError(err));
      this.releaseStream();
    } finally {
      this.starting.set(false);
    }
  }

  /** Arrêter éteint la caméra : pistes coupées, voyant du poste éteint. */
  stop(): void {
    this.running.set(false);
    this.cancelCycle();
    this.releaseStream();
    this.phase.set('idle');
    this.resumeAt.set(null);
  }

  async onDeviceChange(): Promise<void> {
    if (!this.running()) {
      return;
    }
    this.cancelCycle();
    this.releaseStream();
    try {
      await this.openStream();
      this.scheduleNext(0);
    } catch (err) {
      this.cameraError.set(this.describeCameraError(err));
      this.stop();
    }
  }

  clearJournal(): void {
    this.journal.set([]);
  }

  private async openStream(): Promise<void> {
    const video: MediaTrackConstraints =
      this.deviceId !== ''
        ? { deviceId: { exact: this.deviceId } }
        : { width: { ideal: 1280 }, height: { ideal: 720 } };
    this.stream = await navigator.mediaDevices.getUserMedia({ video, audio: false });

    const element = this.video().nativeElement;
    element.srcObject = this.stream;
    await element.play();

    // Les libellés des caméras ne sont exposés qu'une fois l'autorisation donnée.
    const all = await navigator.mediaDevices.enumerateDevices();
    this.devices.set(all.filter((device) => device.kind === 'videoinput'));
    if (this.deviceId === '') {
      this.deviceId = this.stream.getVideoTracks()[0]?.getSettings().deviceId ?? '';
    }
  }

  private releaseStream(): void {
    this.stream?.getTracks().forEach((track) => track.stop());
    this.stream = null;
    this.video().nativeElement.srcObject = null;
  }

  private scheduleNext(delayMs: number): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
    }
    this.timer = setTimeout(() => {
      this.timer = null;
      void this.cycle();
    }, delayMs);
  }

  private cancelCycle(): void {
    if (this.timer !== null) {
      clearTimeout(this.timer);
      this.timer = null;
    }
    this.inFlight?.unsubscribe();
    this.inFlight = null;
    this.generation += 1;
  }

  private async cycle(): Promise<void> {
    if (!this.running()) {
      return;
    }
    // Onglet masqué : personne ne regarde, inutile de dépenser du quota.
    // `onVisibilityChange` relance au retour.
    if (document.hidden) {
      this.phase.set('hidden');
      return;
    }
    this.resumeAt.set(null);

    const generation = this.generation;
    const frame = await this.captureFrame();
    if (!this.running() || generation !== this.generation) {
      return;
    }
    if (frame === null) {
      this.scheduleNext(NOT_READY_RETRY_MS);
      return;
    }

    this.phase.set('detecting');
    this.inFlight = this.searchService
      .detectFaces({
        actorId: this.credentials.actorId,
        bearerToken: this.credentials.bearerToken,
        image: frame,
      })
      .subscribe({
        next: (response) => {
          const used = largestFace(response.faces);
          // Image et visages changent ensemble : jamais les cadres d'une image
          // posés, même un instant, sur la suivante.
          this.setFrame(URL.createObjectURL(frame), response.faces);
          this.usedFaceIndex.set(used?.index ?? null);
          this.cycleError.set(null);

          if (used === null) {
            // Aucun visage : pas de recherche, donc ni quota dépensé ni entrée d'audit.
            this.results.set([]);
            this.searchedThisCycle.set(false);
            this.waitForNextCycle();
            return;
          }
          this.search(frame, used.index);
        },
        error: (err: HttpErrorResponse) => this.onCycleError(err),
      });
  }

  private search(frame: File, faceIndex: number): void {
    this.phase.set('searching');
    this.recordSearch();
    this.inFlight = this.searchService
      .searchByFace({
        actorId: this.credentials.actorId,
        bearerToken: this.credentials.bearerToken,
        image: frame,
        faceIndex,
        threshold: this.threshold ?? undefined,
        limit: this.limit,
      })
      .subscribe({
        next: (response) => {
          this.results.set(response.results);
          this.searchedThisCycle.set(true);
          this.addToJournal(response.results);
          this.waitForNextCycle();
        },
        error: (err: HttpErrorResponse) => this.onCycleError(err),
      });
  }

  private waitForNextCycle(): void {
    this.inFlight = null;
    this.phase.set('waiting');
    this.scheduleNext(this.intervalMs);
  }

  /**
   * Une erreur n'arrête pas la boucle : une API redémarrée doit retrouver un
   * écran qui tourne. Seul le 429 change le rythme, pour ne pas marteler un quota
   * déjà épuisé ; le 401 est traité par `authInterceptor`, qui ferme la session.
   */
  private onCycleError(err: HttpErrorResponse): void {
    this.inFlight = null;
    if (err.status === 429) {
      this.phase.set('throttled');
      this.resumeAt.set(new Date(Date.now() + QUOTA_BACKOFF_MS));
      this.cycleError.set(null);
      this.scheduleNext(QUOTA_BACKOFF_MS);
      return;
    }
    this.cycleError.set(this.describeError(err));
    this.phase.set('waiting');
    this.scheduleNext(this.intervalMs);
  }

  private captureFrame(): Promise<File | null> {
    const element = this.video().nativeElement;
    if (element.videoWidth === 0 || element.videoHeight === 0) {
      return Promise.resolve(null);
    }
    // Résolution native du flux, pas celle d'affichage : la détection doit voir
    // ce que voit la caméra, et les cadres reviennent dans ce repère-là.
    this.canvas.width = element.videoWidth;
    this.canvas.height = element.videoHeight;
    this.canvas.getContext('2d')?.drawImage(element, 0, 0);

    return new Promise((resolve) => {
      this.canvas.toBlob(
        (blob) =>
          resolve(blob === null ? null : new File([blob], 'camera.jpg', { type: 'image/jpeg' })),
        'image/jpeg',
        JPEG_QUALITY,
      );
    });
  }

  private setFrame(url: string | null, faces: QueryFace[]): void {
    const previous = this.frameUrl();
    if (previous !== null) {
      URL.revokeObjectURL(previous);
    }
    this.frameUrl.set(url);
    this.frameFaces.set(faces);
  }

  private recordSearch(): void {
    const now = Date.now();
    this.searchTimes.update((times) => [...times.filter((t) => now - t < 60_000), now]);
  }

  private addToJournal(matches: EventMatch[]): void {
    if (matches.length === 0) {
      return;
    }
    const now = new Date();
    this.journal.update((entries) => {
      const byEvent = new Map(entries.map((entry) => [entry.eventId, entry]));
      for (const match of matches) {
        const known = byEvent.get(match.event_id);
        byEvent.set(match.event_id, {
          eventId: match.event_id,
          best:
            known === undefined || match.confidence > known.best.confidence ? match : known.best,
          hits: (known?.hits ?? 0) + 1,
          lastSeen: now,
        });
      }
      return [...byEvent.values()].sort((a, b) => b.lastSeen.getTime() - a.lastSeen.getTime());
    });
  }

  private describeCameraError(err: unknown): string {
    const name = err instanceof DOMException ? err.name : '';
    switch (name) {
      case 'NotAllowedError':
        return "Accès à la caméra refusé. Autorisez-le dans le navigateur (icône à gauche de l'adresse), puis réessayez.";
      case 'NotFoundError':
      case 'OverconstrainedError':
        return 'Aucune caméra disponible sur ce poste.';
      case 'NotReadableError':
        return 'La caméra est déjà utilisée par une autre application.';
      default:
        return `Impossible d'ouvrir la caméra${name ? ` (${name})` : ''}.`;
    }
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

/** Le plus grand visage par aire de cadre — en pratique, celui qui est devant la caméra. */
function largestFace(faces: QueryFace[]): QueryFace | null {
  let best: QueryFace | null = null;
  for (const face of faces) {
    if (best === null || area(face) > area(best)) {
      best = face;
    }
  }
  return best;
}

function area(face: QueryFace): number {
  const [, , width, height] = face.bbox;
  return (width ?? 0) * (height ?? 0);
}
