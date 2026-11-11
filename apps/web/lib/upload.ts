/** Rules of the file drop zone (components/upload.tsx). */

/**
 * Whether a file matches an ``accept`` list (".pdf,.png", "image/png", "image/*"), as the
 * browser's file picker would filter it: a dropped file is not filtered by the browser.
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
