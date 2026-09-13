import { Component, computed, input, signal } from '@angular/core';

/** Marge autour du visage, en fraction de son côté — un visage sans contexte est illisible. */
const CROP_MARGIN = 0.3;

interface CropPlacement {
  widthPct: number;
  leftPct: number;
  topPct: number;
}

/**
 * Gros plan carré sur un visage d'une photo, sans découpe côté serveur.
 *
 * Raison d'être : sur une vignette de 300 px, un visage de 150 px dans une photo
 * de 4000 px s'affiche sur une dizaine de pixels. Le cadre dit *où* le visage a
 * été trouvé ; ce gros plan dit *qui* — c'est lui qui rend le score vérifiable
 * par un humain, ce que le cadrage seul ne permet pas.
 *
 * L'image est simplement agrandie et décalée dans une fenêtre carrée : le
 * navigateur la tient déjà en cache pour la photo affichée à côté, il n'y a donc
 * ni requête ni découpe supplémentaire.
 */
@Component({
  selector: 'app-face-crop',
  templateUrl: './face-crop.html',
  styleUrl: './face-crop.css',
})
export class FaceCrop {
  readonly src = input.required<string>();
  /** `[x, y, largeur, hauteur]` en pixels de l'image. */
  readonly bbox = input.required<number[]>();
  readonly alt = input('');

  private readonly measurement = signal<{ src: string; width: number; height: number } | null>(
    null,
  );

  /** Mesure liée à la `src` qui l'a produite — voir `FaceFrame` pour le pourquoi. */
  readonly placement = computed<CropPlacement | null>(() => {
    const measured = this.measurement();
    const bbox = this.bbox();
    if (measured === null || measured.src !== this.src() || bbox.length !== 4) {
      return null;
    }

    const [x, y, width, height] = bbox;
    // Fenêtre carrée : la hauteur du conteneur vaut sa largeur, ce qui permet
    // d'exprimer les deux décalages dans la même unité.
    const side = Math.max(width, height) * (1 + 2 * CROP_MARGIN);
    const left = clampWindow(x + width / 2 - side / 2, side, measured.width);
    const top = clampWindow(y + height / 2 - side / 2, side, measured.height);

    return {
      widthPct: (measured.width / side) * 100,
      leftPct: (-left / side) * 100,
      topPct: (-top / side) * 100,
    };
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

/** Ramène la fenêtre dans l'image quand c'est possible, la centre sinon. */
function clampWindow(start: number, side: number, extent: number): number {
  if (side >= extent) {
    return (extent - side) / 2;
  }
  return Math.min(Math.max(start, 0), extent - side);
}
