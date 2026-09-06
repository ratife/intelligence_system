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

/** Miroir d'`IMAGE_EXTENSIONS` (`interface/cli/index_folder.py`). */
const IMAGE_EXTENSIONS = new Set(['jpg', 'jpeg', 'png', 'bmp', 'webp', 'avif', 'tiff', 'tif']);

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
  /** Fichiers écartés parce que ce ne sont pas des images. */
  readonly ignoredNonImages: number;
}

/**
 * Le fichier est-il une image ?
 *
 * `accept="image/*"` ne filtre que la boîte de dialogue — l'utilisateur peut
 * l'outrepasser, et un dépôt par glisser n'y est pas soumis du tout. Le tri se
 * fait donc ici, sur le type MIME quand il est présent, sur l'extension sinon :
 * un fichier déposé arrive parfois sans type selon sa source et le système.
 */
export function isImageFile(file: File): boolean {
  if (file.type.startsWith('image/')) {
    return true;
  }
  const dot = file.name.lastIndexOf('.');
  return dot > 0 && IMAGE_EXTENSIONS.has(file.name.slice(dot + 1).toLowerCase());
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

/** Ajoute les fichiers à la sélection, en écartant les non-images et les doublons. */
export function addPhotos(
  current: readonly SelectedPhoto[],
  files: readonly File[],
): AddPhotosResult {
  const known = new Set(current.map((photo) => photo.key));
  const added: SelectedPhoto[] = [];
  let ignoredDuplicates = 0;
  let ignoredNonImages = 0;

  for (const file of files) {
    if (!isImageFile(file)) {
      ignoredNonImages += 1;
      continue;
    }
    const key = photoKey(file);
    if (known.has(key)) {
      ignoredDuplicates += 1;
      continue;
    }
    known.add(key);
    added.push({ file, key, tooLarge: file.size > MAX_IMAGE_SIZE_BYTES });
  }

  return { photos: [...current, ...added], ignoredDuplicates, ignoredNonImages };
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
