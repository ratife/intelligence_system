import { Component, signal } from '@angular/core';

import { Dashboard } from './dashboard/dashboard';
import { EventImport } from './event-import/event-import';
import { Events } from './events/events';
import { Login } from './login/login';
import { Search } from './search/search';
import { AuthCredentialsService } from './services/auth-credentials.service';

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

@Component({
  selector: 'app-root',
  imports: [Dashboard, Events, Search, EventImport, Login],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  readonly page = signal<Page>('dashboard');
  readonly pages = NAV_ITEMS;

  constructor(readonly credentials: AuthCredentialsService) {}

  selectPage(page: Page): void {
    this.page.set(page);
  }

  logout(): void {
    this.credentials.lock();
    this.page.set('dashboard');
  }
}
