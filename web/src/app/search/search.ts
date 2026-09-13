import { DecimalPipe } from '@angular/common';
import { HttpErrorResponse } from '@angular/common/http';
import { Component, OnDestroy, computed, signal } from '@angular/core';
import { FormsModule } from '@angular/forms';

import { FaceCrop } from '../face-crop/face-crop';
import { FaceBox, FaceFrame } from '../face-frame/face-frame';
import { EventMatch, QueryFace, SearchQueryInfo } from '../models/search.model';
import { AuthCredentialsService } from '../services/auth-credentials.service';
import { SearchService } from '../services/search.service';

interface ResultCard {
  match: EventMatch;
  boxes: FaceBox[];
}

/**
 * Recherche par visage : composer la requête, puis vérifier les résultats.
 *
 * Le fil conducteur des deux moitiés est le même — ne jamais montrer un numéro
 * ou un score sans montrer le visage qui va avec :
 *
 * - **à la composition**, la photo est analysée dès sa sélection et ses visages
 *   sont encadrés. Une photo de groupe se résolvait jusqu'ici par un 409 « et
 *   maintenant précisez `face_index` », sans le moindre moyen de savoir à quoi
 *   correspondait l'index 2. On désigne désormais le visage en cliquant dessus ;
 * - **à la restitution**, chaque événement retrouvé montre où le visage a été
 *   reconnu (cadre) et de quoi il a l'air (gros plan). C'est la contrepartie
 *   visuelle de la règle du domaine : jamais un score sans sa preuve (ADR 010).
 */
@Component({
  selector: 'app-search',
  imports: [FormsModule, DecimalPipe, FaceFrame, FaceCrop],
  templateUrl: './search.html',
  styleUrl: './search.css',
})
export class Search implements OnDestroy {
  threshold: number | null = null;
  dateFrom = '';
  dateTo = '';
  limit = 20;

  /** Signal, et non champ simple : `canSearch` en dépend (mode zoneless). */
  readonly selectedFile = signal<File | null>(null);
  readonly queryPreviewUrl = signal<string | null>(null);

  readonly detecting = signal(false);
  readonly detectError = signal<string | null>(null);
  readonly queryFaces = signal<QueryFace[]>([]);
  readonly selectedFaceIndex = signal<number | null>(null);

  readonly loading = signal(false);
  readonly error = signal<string | null>(null);
  readonly hasSearched = signal(false);
  readonly queryInfo = signal<SearchQueryInfo | null>(null);
  readonly results = signal<EventMatch[]>([]);

  constructor(
    private readonly searchService: SearchService,
    private readonly credentials: AuthCredentialsService,
  ) {}

  ngOnDestroy(): void {
    this.revokePreview();
  }

  readonly selectedFace = computed(
    () => this.queryFaces().find((face) => face.index === this.selectedFaceIndex()) ?? null,
  );

  /** Plusieurs visages : c'est le seul cas où un choix est demandé à l'opérateur. */
  readonly needsFaceChoice = computed(() => this.queryFaces().length > 1);

  readonly canSearch = computed(() => {
    if (this.selectedFile() === null || this.detecting() || this.loading()) {
      return false;
    }
    // Détection injoignable : on laisse tenter la recherche, qui tranchera
    // elle-même (une photo à un seul visage passera très bien sans index).
    if (this.detectError() !== null) {
      return true;
    }
    return this.selectedFaceIndex() !== null;
  });

  /**
   * Cadres de la photo requête : tous les visages, celui retenu mis en avant.
   *
   * Montrer aussi les visages écartés est le point : l'opérateur voit que le
   * système en a trouvé d'autres et qu'il a choisi celui-là — pas une boîte
   * noire qui aurait pu chercher n'importe qui.
   */
  readonly queryBoxes = computed<FaceBox[]>(() => {
    const faces = this.queryFaces();
    const selected = this.selectedFaceIndex();

    if (faces.length > 0) {
      return faces.map((face) => ({
        index: face.index,
        bbox: face.bbox,
        tone: face.index === selected ? ('selected' as const) : ('other' as const),
        label: faces.length > 1 ? `#${face.index}` : '',
        title:
          face.index === selected
            ? `Visage #${face.index} retenu pour la recherche`
            : `Rechercher le visage #${face.index}`,
      }));
    }

    // Repli quand la détection préalable a échoué mais que la recherche, elle,
    // a répondu : elle indique le visage utilisé, autant l'encadrer.
    const used = this.queryInfo()?.face_used;
    if (used === undefined) {
      return [];
    }
    return [
      {
        index: used.index,
        bbox: used.bbox,
        tone: 'selected' as const,
        label: '',
        title: 'Visage utilisé pour la recherche',
      },
    ];
  });

  readonly resultCards = computed<ResultCard[]>(() =>
    this.results().map((match) => ({
      match,
      boxes: [
        {
          index: match.evidence.image_id,
          bbox: match.evidence.bbox,
          tone: 'match' as const,
          label: match.evidence.similarity.toFixed(2),
          title: `Visage reconnu — similarité ${match.evidence.similarity.toFixed(2)}`,
        },
      ],
    })),
  );

  onFileSelected(event: Event): void {
    const input = event.target as HTMLInputElement;
    const file = input.files?.[0] ?? null;

    this.revokePreview();
    this.selectedFile.set(file);
    this.resetQueryState();

    if (file === null) {
      this.queryPreviewUrl.set(null);
      return;
    }
    this.queryPreviewUrl.set(URL.createObjectURL(file));
    this.detectQueryFaces(file);
  }

  /** Changer de visage invalide les résultats précédents : ils portaient sur un autre. */
  selectFace(index: number): void {
    if (index === this.selectedFaceIndex()) {
      return;
    }
    this.selectedFaceIndex.set(index);
    this.clearResults();
  }

  onSubmit(): void {
    const file = this.selectedFile();
    if (file === null) {
      this.error.set("Sélectionnez d'abord une photo.");
      return;
    }

    this.loading.set(true);
    this.error.set(null);

    this.searchService
      .searchByFace({
        actorId: this.credentials.actorId,
        bearerToken: this.credentials.bearerToken,
        image: file,
        faceIndex: this.selectedFaceIndex() ?? undefined,
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

  private detectQueryFaces(file: File): void {
    this.detecting.set(true);
    this.searchService
      .detectFaces({
        actorId: this.credentials.actorId,
        bearerToken: this.credentials.bearerToken,
        image: file,
      })
      .subscribe({
        next: (response) => {
          this.queryFaces.set(response.faces);
          // Un seul visage : rien à désambiguïser, on le retient d'emblée.
          this.selectedFaceIndex.set(response.faces.length === 1 ? response.faces[0].index : null);
          this.detecting.set(false);
        },
        error: (err: HttpErrorResponse) => {
          this.detectError.set(this.describeError(err));
          this.detecting.set(false);
        },
      });
  }

  private resetQueryState(): void {
    this.queryFaces.set([]);
    this.selectedFaceIndex.set(null);
    this.detectError.set(null);
    this.error.set(null);
    this.clearResults();
  }

  private clearResults(): void {
    this.hasSearched.set(false);
    this.queryInfo.set(null);
    this.results.set([]);
  }

  private revokePreview(): void {
    const url = this.queryPreviewUrl();
    if (url !== null) {
      URL.revokeObjectURL(url);
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
