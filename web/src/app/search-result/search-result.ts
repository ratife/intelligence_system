import { DecimalPipe } from '@angular/common';
import { Component, computed, input } from '@angular/core';

import { FaceCrop } from '../face-crop/face-crop';
import { FaceBox, FaceFrame } from '../face-frame/face-frame';
import { EventMatch } from '../models/search.model';

/**
 * Un événement retrouvé, avec sa preuve : où le visage a été reconnu (cadre) et
 * de quoi il a l'air (gros plan). Contrepartie visuelle de la règle du domaine,
 * jamais un score sans sa preuve (ADR 010).
 *
 * Partagé par la recherche par photo et la recherche caméra, pour que la façon
 * de prouver un résultat ne puisse pas diverger d'un écran à l'autre.
 */
@Component({
  selector: 'app-search-result',
  imports: [DecimalPipe, FaceFrame, FaceCrop],
  templateUrl: './search-result.html',
  styleUrl: './search-result.css',
})
export class SearchResult {
  readonly match = input.required<EventMatch>();

  readonly boxes = computed<FaceBox[]>(() => {
    const evidence = this.match().evidence;
    return [
      {
        index: evidence.image_id,
        bbox: evidence.bbox,
        tone: 'match',
        label: evidence.similarity.toFixed(2),
        title: `Visage reconnu — similarité ${evidence.similarity.toFixed(2)}`,
      },
    ];
  });
}
