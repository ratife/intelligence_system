/**
 * Extraction des fichiers d'un glisser-déposer, dossiers compris.
 *
 * `DataTransfer.files` ne contient que des fichiers : déposer un dossier n'y
 * produit rien d'exploitable. Or déposer le dossier d'un événement est
 * précisément le geste attendu. L'API `webkitGetAsEntry` permet de le parcourir ;
 * là où elle manque, on retombe sur `DataTransfer.files`, qui couvre au moins
 * le dépôt de fichiers.
 *
 * Deux contraintes de cette API, faciles à manquer :
 *
 * - les entrées doivent être **récupérées de façon synchrone** dans le
 *   gestionnaire d'événement : le `DataTransfer` est vidé dès qu'il rend la
 *   main, donc tout `await` placé avant la collecte perd le contenu du dépôt ;
 * - `readEntries` ne renvoie qu'un **lot** à la fois (100 entrées sur Chromium).
 *   Sans rappel jusqu'au lot vide, un dossier de 300 photos en livrerait 100,
 *   silencieusement.
 */

/** Garde-fou contre une arborescence profonde ou cyclique (liens symboliques). */
const MAX_DIRECTORY_DEPTH = 8;

/** Les fichiers déposés, dossiers parcourus. L'ordre suit celui du dépôt. */
export async function filesFromDrop(dataTransfer: DataTransfer): Promise<File[]> {
  const entries = collectEntries(dataTransfer);
  if (entries === null) {
    return Array.from(dataTransfer.files);
  }

  const files: File[] = [];
  for (const entry of entries) {
    await collectFromEntry(entry, files, 0);
  }
  return files;
}

/** Synchrone par obligation : le `DataTransfer` ne survit pas au gestionnaire. */
function collectEntries(dataTransfer: DataTransfer): FileSystemEntry[] | null {
  const items = dataTransfer.items;
  if (items === undefined || items.length === 0) {
    return null;
  }

  const entries: FileSystemEntry[] = [];
  for (let index = 0; index < items.length; index += 1) {
    const item = items[index];
    if (typeof item.webkitGetAsEntry !== 'function') {
      return null;
    }
    const entry = item.webkitGetAsEntry();
    if (entry !== null) {
      entries.push(entry);
    }
  }
  return entries.length > 0 ? entries : null;
}

async function collectFromEntry(
  entry: FileSystemEntry,
  into: File[],
  depth: number,
): Promise<void> {
  if (entry.isFile) {
    const file = await fileFromEntry(entry as FileSystemFileEntry);
    if (file !== null) {
      into.push(file);
    }
    return;
  }
  if (entry.isDirectory && depth < MAX_DIRECTORY_DEPTH) {
    for (const child of await readAllEntries(entry as FileSystemDirectoryEntry)) {
      await collectFromEntry(child, into, depth + 1);
    }
  }
}

/** Un fichier illisible (droits, support retiré) est ignoré, pas fatal au dépôt. */
function fileFromEntry(entry: FileSystemFileEntry): Promise<File | null> {
  return new Promise((resolve) => {
    entry.file(
      (file) => resolve(file),
      () => resolve(null),
    );
  });
}

function readAllEntries(directory: FileSystemDirectoryEntry): Promise<FileSystemEntry[]> {
  return new Promise((resolve) => {
    const reader = directory.createReader();
    const all: FileSystemEntry[] = [];

    const readNextBatch = (): void => {
      reader.readEntries(
        (batch) => {
          if (batch.length === 0) {
            resolve(all);
            return;
          }
          all.push(...batch);
          readNextBatch();
        },
        () => resolve(all),
      );
    };

    readNextBatch();
  });
}
