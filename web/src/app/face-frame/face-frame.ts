import { Component, computed, input, output, signal } from '@angular/core';

/** Rôle d'un cadre — porté aussi par son intitulé, jamais par la couleur seule. */
export type FaceTone = 'selected' | 'other' | 'match';

export interface FaceBox {
  /** Index du visage tel que l'API le connaît (`face_index`). */
  index: number;
  /** `[x, y, largeur, hauteur]` en pixels de l'image, tel que renvoyé par l'API. */
  bbox: number[];
  tone: FaceTone;
  /** Intitulé affiché sur le cadre. Vide = pas de pastille. */
  label: string;
  /** Infobulle et libellé accessible du bouton, quand le cadre est cliquable. */
  title: string;
}

interface PlacedBox extends FaceBox {
  leftPct: number;
  topPct: number;
  widthPct: number;
  heightPct: number;
}

/**
 * Une image et les cadres de ses visages.
 *
 * Les cadres arrivent en pixels de l'image décodée ; ils sont convertis en
 * pourcentages des dimensions naturelles, ce qui les rend indépendants de la
 * taille d'affichage — l'image peut être réduite, la page redimensionnée, les
 * cadres suivent sans recalcul.
 *
 * Deux détails dont dépend la justesse du positionnement :
 *
 * - **le conteneur épouse exactement l'image** (`inline-block`), sinon un
 *   letterboxing décalerait tous les cadres ;
 * - **la mesure est associée à la `src` qui l'a produite** : sans cela, changer
 *   de photo afficherait brièvement les nouveaux cadres sur les dimensions de
 *   l'ancienne image.
 *
 * L'orientation EXIF n'appelle aucune correction : OpenCV (côté détection) et le
 * navigateur l'appliquent tous les deux, les deux systèmes de coordonnées
 * coïncident donc.
 */
@Component({
  selector: 'app-face-frame',
  templateUrl: './face-frame.html',
  styleUrl: './face-frame.css',
})
export class FaceFrame {
  readonly src = input.required<string>();
  readonly alt = input('');
  readonly boxes = input<FaceBox[]>([]);
  readonly selectable = input(false);
  readonly boxSelected = output<number>();

  private readonly measurement = signal<{ src: string; width: number; height: number } | null>(
    null,
  );

  /** Dimensions naturelles, ignorées si elles proviennent d'une image précédente. */
  private readonly size = computed(() => {
    const measured = this.measurement();
    return measured !== null && measured.src === this.src() ? measured : null;
  });

  readonly placed = computed<PlacedBox[]>(() => {
    const size = this.size();
    if (size === null) {
      return [];
    }
    return this.boxes()
      .filter((box) => box.bbox.length === 4)
      .map((box) => {
        const [x, y, width, height] = box.bbox;
        return {
          ...box,
          leftPct: (x / size.width) * 100,
          topPct: (y / size.height) * 100,
          widthPct: (width / size.width) * 100,
          heightPct: (height / size.height) * 100,
        };
      });
  });

  onLoad(event: Event): void {
    const img = event.target as HTMLImageElement;
    this.measurement.set({
      src: this.src(),
      width: img.naturalWidth,
      height: img.naturalHeight,
    });
  }
}
