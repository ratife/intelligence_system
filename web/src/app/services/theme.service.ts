import { computed, effect, Injectable, signal } from '@angular/core';

const THEME_STORAGE_KEY = 'facereco.theme';

/** Trois états et non deux : « système » doit rester joignable. */
export type ThemeChoice = 'system' | 'light' | 'dark';

const CYCLE: readonly ThemeChoice[] = ['system', 'light', 'dark'];

/**
 * Thème de l'interface.
 *
 * Le choix se garde en `localStorage` et non `sessionStorage` — contrairement
 * aux identifiants, une préférence d'affichage n'a aucune raison d'expirer à la
 * fermeture du navigateur, et elle n'est pas sensible.
 *
 * « Système » n'est pas un troisième thème mais l'absence de choix : tant qu'il
 * est actif, un changement de réglage du système d'exploitation (bascule
 * automatique au coucher du soleil, par exemple) est suivi en direct, d'où
 * l'écoute de `matchMedia` plutôt qu'une simple lecture au démarrage.
 *
 * L'attribut est aussi posé par un script en ligne dans `index.html`, avant le
 * premier rendu : appliqué seulement ici, le temps de chargement du bundle
 * Angular laisserait apparaître un écran clair avant de basculer.
 */
@Injectable({ providedIn: 'root' })
export class ThemeService {
  readonly choice = signal<ThemeChoice>(readStoredChoice());

  /** Vrai thème appliqué, une fois « système » résolu. */
  readonly resolved = computed<'light' | 'dark'>(() => {
    const choice = this.choice();
    if (choice !== 'system') {
      return choice;
    }
    return this.systemPrefersDark() ? 'dark' : 'light';
  });

  private readonly systemPrefersDark = signal(prefersDark());

  constructor() {
    // Signal, et pas un champ : l'écouteur se déclenche hors de tout gestionnaire
    // de template, et en mode zoneless seule une écriture de signal redessine.
    matchDarkQuery()?.addEventListener('change', (event) =>
      this.systemPrefersDark.set(event.matches),
    );

    effect(() => {
      document.documentElement.dataset['theme'] = this.resolved();
      writeStoredChoice(this.choice());
    });
  }

  /** Système → clair → sombre → système. Un seul bouton, trois états. */
  next(): void {
    const index = CYCLE.indexOf(this.choice());
    this.choice.set(CYCLE[(index + 1) % CYCLE.length]);
  }
}

function matchDarkQuery(): MediaQueryList | null {
  return typeof matchMedia === 'function' ? matchMedia('(prefers-color-scheme: dark)') : null;
}

function prefersDark(): boolean {
  return matchDarkQuery()?.matches ?? false;
}

// `localStorage` peut lever (navigation privée, stockage bloqué) : une
// préférence non retenue est acceptable, une interface qui plante ne l'est pas.
function readStoredChoice(): ThemeChoice {
  try {
    const stored = localStorage.getItem(THEME_STORAGE_KEY);
    return stored === 'light' || stored === 'dark' ? stored : 'system';
  } catch {
    return 'system';
  }
}

function writeStoredChoice(choice: ThemeChoice): void {
  try {
    if (choice === 'system') {
      localStorage.removeItem(THEME_STORAGE_KEY);
    } else {
      localStorage.setItem(THEME_STORAGE_KEY, choice);
    }
  } catch {
    /* préférence non retenue : sans effet sur l'écran courant */
  }
}
