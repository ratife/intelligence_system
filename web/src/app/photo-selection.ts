/**
 * Sélection de photos avant import : on **ajoute**, on ne remplace pas.
 *
 * Un `<input type="file">` remplace intégralement sa sélection à chaque
 * passage : choisir trois photos puis rouvrir le sélecteur pour en ajouter deux
 * faisait perdre les trois premières. Un import d'événement se compose pourtant
 * rarement en un seul geste — plusieurs dossiers, plusieurs appareils, un oubli
 * à rattraper. D'où cette accumulation, et la possibilité de retirer une photo
 * choisie par erreur sans tout refaire.
 *
 * Ces fonctions sont pures : elles décrivent la sélection, le composant se
 * contente de la porter dans un signal.
 */

/** Miroir de `MAX_IMAGE_SIZE_BYTES` (`interface/api/routers/admin_events.py`). */
export const MAX_IMAGE_SIZE_BYTES = 10 * 1024 * 1024;

export interface SelectedPhoto {
  readonly file: File;
  /** Identité de la photo dans la sélection — sert de clé de suivi et de retrait. */
  readonly key: string;
  /** L'API refuserait le fichier (413) : autant le dire avant de lancer la file. */
  readonly tooLarge: boolean;
}

export interface AddPhotosResult {
  readonly photos: SelectedPhoto[];
  /** Fichiers écartés parce que déjà dans la sélection — à signaler, pas à taire. */
  readonly ignoredDuplicates: number;
}

/**
 * Identité d'un fichier local : nom, taille et date de modification.
 *
 * Heuristique, et suffisante ici — elle empêche seulement d'ajouter deux fois
 * le *même* fichier en deux gestes. La garantie réelle reste côté serveur, qui
 * dédoublonne sur le hash du contenu (`event_images.content_hash`) et répond
 * « doublon » quel que soit le nom du fichier.
 */
export function photoKey(file: File): string {
  return `${file.name}|${file.size}|${file.lastModified}`;
}

/** Ajoute les fichiers à la sélection, en ignorant ceux déjà présents. */
export function addPhotos(
  current: readonly SelectedPhoto[],
  files: readonly File[],
): AddPhotosResult {
  const known = new Set(current.map((photo) => photo.key));
  const added: SelectedPhoto[] = [];
  let ignoredDuplicates = 0;

  for (const file of files) {
    const key = photoKey(file);
    if (known.has(key)) {
      ignoredDuplicates += 1;
      continue;
    }
    known.add(key);
    added.push({ file, key, tooLarge: file.size > MAX_IMAGE_SIZE_BYTES });
  }

  return { photos: [...current, ...added], ignoredDuplicates };
}

export function totalSizeBytes(photos: readonly SelectedPhoto[]): number {
  return photos.reduce((total, photo) => total + photo.file.size, 0);
}

/** Tailles lisibles à l'œil : `840 Ko`, `2,4 Mo`. */
export function formatFileSize(bytes: number): string {
  if (bytes < 1024) {
    return `${bytes} o`;
  }
  const kilobytes = bytes / 1024;
  if (kilobytes < 1024) {
    return `${Math.round(kilobytes)} Ko`;
  }
  return `${(kilobytes / 1024).toFixed(1).replace('.', ',')} Mo`;
}
