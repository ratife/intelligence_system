/**
 * État de progression de l'indexation, côté client.
 *
 * L'API d'import (`POST /api/v1/admin/events/{id}/images`) indexe les images de
 * façon synchrone et ne rend la main qu'une fois le lot terminé : la
 * granularité de progression vient donc du client, qui pousse les images une
 * par une et compose lui-même l'avancement à partir des réponses successives.
 */

export type ImportItemStatus =
  'pending' | 'uploading' | 'indexing' | 'indexed' | 'duplicate' | 'error' | 'cancelled';

/** Une image de la file d'import, du moment où elle est sélectionnée à son issue. */
export interface ImportItem {
  readonly filename: string;
  readonly sizeBytes: number;
  readonly status: ImportItemStatus;
  /** Fraction de l'envoi réseau déjà transmise (0 → 1), pertinente pendant `uploading`. */
  readonly uploadedRatio: number;
  readonly imageId: number | null;
  readonly facesAccepted: number;
  readonly facesRejected: number;
  readonly error: string | null;
  readonly durationMs: number | null;
}

const TERMINAL_STATUSES: ReadonlySet<ImportItemStatus> = new Set<ImportItemStatus>([
  'indexed',
  'duplicate',
  'error',
  'cancelled',
]);

/** Vrai lorsque l'image ne bougera plus : elle compte dans l'avancement. */
export function isTerminalStatus(status: ImportItemStatus): boolean {
  return TERMINAL_STATUSES.has(status);
}

export function createImportItem(file: File): ImportItem {
  return {
    filename: file.name,
    sizeBytes: file.size,
    status: 'pending',
    uploadedRatio: 0,
    imageId: null,
    facesAccepted: 0,
    facesRejected: 0,
    error: null,
    durationMs: null,
  };
}
