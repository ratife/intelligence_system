import { Component, signal } from '@angular/core';

import { EventImport } from './event-import/event-import';
import { Search } from './search/search';

type Page = 'search' | 'import';

@Component({
  selector: 'app-root',
  imports: [Search, EventImport],
  templateUrl: './app.html',
  styleUrl: './app.css',
})
export class App {
  readonly page = signal<Page>('search');

  selectPage(page: Page): void {
    this.page.set(page);
  }
}
