/**
 * Mise en forme des motifs de rejet qualité, partagée par les écrans qui les affichent.
 *
 * Transformation générique (souligné → espace, opérateur aéré) plutôt qu'une
 * table de correspondance : les motifs sont construits côté domaine avec le
 * seuil franchi (`domain/value_objects/quality.py`), une table se
 * désynchroniserait en silence au moindre changement de seuil ou de critère.
 */
export function humanizeRejectionReason(reason: string): string {
  const spaced = reason.replace(/_/g, ' ').replace(/([<>]=?)/g, ' $1 ');
  return (spaced.charAt(0).toUpperCase() + spaced.slice(1)).replace(/\s+/g, ' ').trim();
}
