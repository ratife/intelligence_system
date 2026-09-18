import { Component, signal } from '@angular/core';

import { Dashboard } from './dashboard/dashboard';
import { EventImport } from './event-import/event-import';
import { Events } from './events/events';
import { Login } from './login/login';
import { Search } from './search/search';
import { AuthCredentialsService } from './services/auth-credentials.service';
import { ThemeChoice, ThemeService } from './services/theme.service';

type Page = 'dashboard' | 'events' | 'search' | 'import';

interface NavItem {
  readonly id: Page;
  readonly label: string;
  readonly icon: string;
}

/* Tracés SVG plutôt que des glyphes : le rail réduit n'affiche plus que l'icône,
   et un caractère absent de la police y laisserait un carré vide sans recours.
   Dessinés sur une grille de 20, en `currentColor`, donc ils suivent le thème. */
const NAV_ITEMS: readonly NavItem[] = [
  {
    id: 'dashboard',
    label: 'Tableau de bord',
    icon: 'M3.5 3.5h5v5h-5zM11.5 3.5h5v5h-5zM3.5 11.5h5v5h-5zM11.5 11.5h5v5h-5z',
  },
  {
    id: 'events',
    label: 'Événements',
    icon: 'M3.5 5.5h13v11h-13zM3.5 9h13M7 3.5v3M13 3.5v3',
  },
  {
    id: 'search',
    label: 'Recherche',
    icon: 'M12.5 12.5 16.5 16.5M8.75 14a5.25 5.25 0 1 1 0-10.5 5.25 5.25 0 0 1 0 10.5z',
  },
  {
    id: 'import',
    label: 'Importer un événement',
    icon: 'M10 13V3.5m0 0L6.5 7M10 3.5 13.5 7M3.5 13v2.5a1 1 0 0 0 1 1h11a1 1 0 0 0 1-1V13',
  },
];

/* Un état, son libellé, son icône. « Système » se dessine en écran plutôt qu'en
   demi-soleil : la bascule automatique est une propriété de la machine, pas une
   troisième ambiance. */
const THEME_LABELS: Record<ThemeChoice, string> = {
  system: 'Thème : système',
  light: 'Thème : clair',
  dark: 'Thème : sombre',
};

const THEME_ICONS: Record<ThemeChoice, string> = {
  system: 'M3.5 4.5h13v9h-13zM7.5 16.5h5M10 13.5v3',
  light:
    'M10 4.5v-2M10 17.5v-2M4.5 10h-2M17.5 10h-2M6.1 6.1 4.7 4.7M15.3 15.3l-1.4-1.4' +
    'M13.9 6.1l1.4-1.4M6.1 13.9l-1.4 1.4M14 10a4 4 0 1 1-8 0 4 4 0 0 1 8 0z',
  dark: 'M16 12.3A6.8 6.8 0 0 1 7.7 4a6.5 6.5 0 1 0 8.3 8.3z',
};

@Component({
  selector: 'app-root',
  imports: [Dashboard, Events, Search, EventImport, Login],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  readonly page = signal<Page>('dashboard');
  readonly pages = NAV_ITEMS;

  constructor(
    readonly credentials: AuthCredentialsService,
    readonly theme: ThemeService,
  ) {}

  themeLabel(): string {
    return THEME_LABELS[this.theme.choice()];
  }

  themeIcon(): string {
    return THEME_ICONS[this.theme.choice()];
  }

  selectPage(page: Page): void {
    this.page.set(page);
  }

  logout(): void {
    this.credentials.lock();
    this.page.set('dashboard');
  }
}
