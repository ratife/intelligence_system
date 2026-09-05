/**
 * Miroir TypeScript des schemas de `interface/api/routers/indexing.py`.
 * Pas de codegen : à mettre à jour en même temps que le schéma Pydantic.
 */

export interface TriggerIndexingResult {
  /** Nombre d'images publiées en file — elles ne sont pas indexées pour autant. */
  images_published: number;
}
