import { Component, signal } from '@angular/core';

import { Dashboard } from './dashboard/dashboard';
import { EventImport } from './event-import/event-import';
import { Events } from './events/events';
import { Login } from './login/login';
import { Search } from './search/search';
import { AuthCredentialsService } from './services/auth-credentials.service';

type Page = 'dashboard' | 'events' | 'search' | 'import';

@Component({
  selector: 'app-root',
  imports: [Dashboard, Events, Search, EventImport, Login],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  readonly page = signal<Page>('dashboard');

  constructor(readonly credentials: AuthCredentialsService) {}

  selectPage(page: Page): void {
    this.page.set(page);
  }

  logout(): void {
    this.credentials.lock();
    this.page.set('dashboard');
  }
}
