import { Component, computed, input, output } from '@angular/core';

import { FaceBox, FaceFrame } from '../face-frame/face-frame';
import { EventDetail, EventImage } from '../models/event-catalog.model';
import { humanizeRejectionReason } from '../rejection-reason';

interface StatusBadge {
  label: string;
  icon: string;
  tone: string;
}

/** Statuts d'indexation (`IndexStatus`), jamais portés par la couleur seule. */
const STATUS_BADGES: Record<string, StatusBadge> = {
  done: { label: 'Indexée', icon: '✓', tone: 'good' },
  pending: { label: 'En attente', icon: '○', tone: 'accent' },
  failed: { label: 'Échec', icon: '✕', tone: 'critical' },
  skipped: { label: 'Ignorée', icon: '–', tone: 'muted' },
};

interface ImageCard {
  image: EventImage;
  boxes: FaceBox[];
  status: StatusBadge;
}

/**
 * Détail d'un événement : ce que l'indexation a retenu, et ce qu'elle a écarté.
 *
 * Purement présentationnel — le parent charge, ce composant affiche.
 *
 * Les visages retenus sont encadrés sur leur photo ; les visages écartés sont
 * seulement listés avec leur motif, parce que `rejected_faces` ne conserve pas
 * leur cadre (ni `bbox` ni dimensions en base). C'est la raison d'être de cette
 * asymétrie à l'écran : elle reflète ce que la base sait, pas un choix de
 * présentation.
 */
@Component({
  selector: 'app-event-detail',
  imports: [FaceFrame],
  templateUrl: './event-detail.html',
  styleUrl: './event-detail.css',
})
export class EventDetailView {
  readonly detail = input.required<EventDetail>();
  readonly closed = output<void>();

  readonly imageCards = computed<ImageCard[]>(() =>
    this.detail().images.map((image) => ({
      image,
      status: STATUS_BADGES[image.index_status] ?? {
        label: image.index_status,
        icon: '?',
        tone: 'muted',
      },
      boxes: image.indexed_faces.map((face) => ({
        index: face.face_index,
        bbox: face.bbox,
        tone: 'match' as const,
        label: `#${face.face_index}`,
        title:
          `Visage #${face.face_index} indexé — détection ${face.detection_score.toFixed(2)}, ` +
          `qualité ${face.quality_score.toFixed(2)}`,
      })),
    })),
  );

  /** Part-à-tout des visages détectés : retenus vs écartés par le filtre qualité (§6.1). */
  readonly faceSegments = computed(() => {
    const summary = this.detail().event;
    return [
      { label: 'Retenus', icon: '✓', tone: 'good', count: summary.face_count },
      { label: 'Écartés', icon: '⚠', tone: 'warning', count: summary.discarded_face_count },
    ].filter((segment) => segment.count > 0);
  });

  readonly detectedFaceCount = computed(
    () => this.detail().event.face_count + this.detail().event.discarded_face_count,
  );

  percent(rate: number): number {
    return Math.round(rate * 100);
  }

  /**
   * `2026-03-14` → `14/03/2026`, sans passer par `Date`.
   *
   * `new Date('2026-03-14')` est interprété en UTC : affiché dans un fuseau
   * négatif, il reculerait d'un jour. Une date d'événement n'a pas de fuseau.
   */
  formatDate(isoDate: string): string {
    const [year, month, day] = isoDate.split('-');
    return day && month && year ? `${day}/${month}/${year}` : isoDate;
  }

  /** Horodatage d'indexation : celui-ci a bien un instant, donc un fuseau. */
  formatTimestamp(iso: string): string {
    const parsed = new Date(iso);
    return Number.isNaN(parsed.getTime())
      ? iso
      : parsed.toLocaleString('fr-FR', {
          day: '2-digit',
          month: '2-digit',
          year: 'numeric',
          hour: '2-digit',
          minute: '2-digit',
        });
  }

  /** `taille_visage<40px` → « Taille visage < 40px » — même règle que le tableau de bord. */
  humanizeReason(reason: string): string {
    return humanizeRejectionReason(reason);
  }
}
