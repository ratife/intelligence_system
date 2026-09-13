/**
 * Miroir TypeScript des schemas de `interface/api/schemas/workers.py`.
 * Pas de codegen : à mettre à jour en même temps que le schéma Pydantic.
 */

export interface Worker {
  name: string;
  pending_messages: number;
  /** Depuis le dernier sondage de la file — le seul signal de vie disponible. */
  idle_seconds: number;
  /** Depuis la dernière lecture réussie ; élevé sans être anormal si rien à faire. */
  inactive_seconds: number;
  is_active: boolean;
  is_working: boolean;
}

export interface QueueStatus {
  consumer_group: string;
  workers: Worker[];
  active_worker_count: number;
  undelivered_messages: number;
  unacknowledged_messages: number;
  dead_letter_messages: number;
  backlog: number;
  /** Du travail en attente et aucun consommateur actif pour le prendre. */
  is_stalled: boolean;
}
