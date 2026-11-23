/** Rules of the file drop zone (components/upload.tsx). */

/**
 * Whether a file matches an ``accept`` list (".pdf,.png", "image/png", "image/*"). The zone
 * checks every file itself, picked or dropped: its picker has no ``accept`` (a phone greys out a
 * PDF that a site sent as « unknown »), and an extension that matches is enough.
 */
export function acceptsFile(
  name: string,
  type: string,
  accept: string | undefined,
): boolean {
  if (!accept) return true;
  const lower = name.toLowerCase();
  return accept
    .split(",")
    .map((a) => a.trim().toLowerCase())
    .filter(Boolean)
    .some((a) =>
      a.startsWith(".")
        ? lower.endsWith(a)
        : a.endsWith("/*")
          ? type.toLowerCase().startsWith(a.slice(0, -1))
          : type.toLowerCase() === a,
    );
}

/** "Kbis.pdf prêt à être déposé", "3 fichiers prêts à être déposés : a.pdf, b.pdf…". */
export function readyText(names: string[]): string {
  if (names.length === 1) return `${names[0]} prêt à être déposé`;
  const shown = names.slice(0, 3).join(", ");
  return `${names.length} fichiers prêts à être déposés : ${shown}${names.length > 3 ? "…" : ""}`;
}

/** What a dropped item gives (``webkitGetAsEntry``): a file, or a folder to walk through. */
export type DroppedEntry = {
  isFile: boolean;
  isDirectory: boolean;
  name: string;
  file?: (ok: (f: File) => void, ko?: (e: unknown) => void) => void;
  createReader?: () => {
    readEntries: (
      ok: (e: DroppedEntry[]) => void,
      ko?: (e: unknown) => void,
    ) => void;
  };
};

/** Every file of the dropped entries, folders and sub-folders included (AWS: « Pièces
 * communes » and several ZIPs dropped at once). */
export async function collectFiles(entries: DroppedEntry[]): Promise<File[]> {
  const out: File[] = [];
  for (const entry of entries) {
    if (entry.isFile && entry.file) {
      const read = entry.file;
      out.push(await new Promise<File>((ok, ko) => read(ok, ko)));
    } else if (entry.isDirectory && entry.createReader) {
      const reader = entry.createReader();
      // a folder gives its entries in batches (100 in Chrome) until an empty one
      for (;;) {
        const batch = await new Promise<DroppedEntry[]>((ok, ko) =>
          reader.readEntries(ok, ko),
        );
        if (batch.length === 0) break;
        out.push(...(await collectFiles(batch)));
      }
    }
  }
  return out;
}

/** The files chosen so far plus the new ones (picked one by one), without the same file twice. */
export function mergeFiles(chosen: File[], added: File[]): File[] {
  const key = (f: File) => `${f.name}|${f.size}`;
  const seen = new Set(chosen.map(key));
  const out = [...chosen];
  for (const f of added)
    if (!seen.has(key(f))) {
      seen.add(key(f));
      out.push(f);
    }
  return out;
}
