/**
 * Rules of the consultations (ADR-052): a general contractor asks the company for a quote on
 * part of a lot. The dossier is lighter (Documents reçus · Prix · Devis), prices come
 * from « Ma liste de prix » or the company, the quote cites the CCTP. Pure functions.
 */
import { parseEuros } from "@/lib/format";
import type {
  Bid,
  BidKind,
  ConsultationRead,
  Inclusion,
  QuoteState,
  ServiceIn,
} from "@/lib/types";

export const KIND_LABELS: Record<BidKind, string> = {
  tender: "Appel d'offres",
  consultation: "Consultation (devis)",
};

/** The same units as the server (app/db/models/pricing.py PRICE_UNITS). */
export const PRICE_UNITS = [
  "m²",
  "ml",
  "m³",
  "heure",
  "jour",
  "forfait",
  "u",
  "passage",
  "mois",
] as const;

/** A rubrique kept (« Chiffrée par nous ») or set aside; the others stay as they were. */
export function toggleSection(
  excluded: string[],
  section: string,
  priced: boolean,
): string[] {
  if (priced) return excluded.filter((s) => s !== section);
  return excluded.includes(section) ? excluded : [...excluded, section];
}

export type ServiceRow = {
  name: string;
  unit: string;
  price: string;
  description: string;
};

const blank = (r: ServiceRow) =>
  !r.name.trim() && !r.price.trim() && !r.description.trim();

/** Row index → what is wrong with it (blank rows are dropped, never wrong). */
export function serviceErrors(rows: ServiceRow[]): Record<number, string> {
  const errors: Record<number, string> = {};
  rows.forEach((r, i) => {
    if (blank(r)) return;
    if (!r.name.trim()) errors[i] = "Nom de la prestation manquant.";
    else if (parseEuros(r.price) === null)
      errors[i] = "Prix invalide (ex. : 1,50).";
  });
  return errors;
}

export function servicesFromRows(rows: ServiceRow[]): ServiceIn[] {
  return rows
    .filter((r) => !blank(r))
    .map((r) => ({
      name: r.name.trim(),
      unit: r.unit,
      price_cents: parseEuros(r.price) ?? 0,
      description: r.description.trim() || null,
    }));
}

/** « 20 % », « 5,5 % » from basis points. */
export function vatLabel(bp: number): string {
  const whole = Math.floor(bp / 100);
  const rest = bp % 100;
  if (rest === 0) return `${whole} %`;
  return `${whole},${String(rest).padStart(2, "0").replace(/0$/, "")} %`;
}

export function inclusionSource(i: Inclusion): string {
  return i.file && i.page ? `${i.file}, p. ${i.page}` : "ajoutée par vous";
}

export type QuoteAction =
  "blocked" | "prepare_paid" | "prepare_free" | "drafting" | "ready" | "error";

/** What the « Devis » tab offers now. */
export function quoteAction(state: QuoteState): QuoteAction {
  const q = state.quote;
  if (q?.status === "drafting") return "drafting";
  if (q?.status === "ready") return "ready";
  if (state.blocking) return "blocked";
  if (q?.status === "error") return "error";
  return state.cctp ? "prepare_paid" : "prepare_free";
}

/** The rubriques of a price file, each once, in the file's order (a line without one aside). */
export function sectionsOf(lines: { section: string }[]): string[] {
  const out: string[] = [];
  for (const { section } of lines)
    if (section && !out.includes(section)) out.push(section);
  return out;
}

/** The rubriques set aside when only ``chosen`` are priced. */
export function excludedFromChosen(all: string[], chosen: string[]): string[] {
  return all.filter((s) => !chosen.includes(s));
}

/** The picker's button: « 1 rubrique chiffrée sur 13 ». */
export function chosenLabel(all: string[], excluded: string[]): string {
  const n = all.filter((s) => !excluded.includes(s)).length;
  if (n === all.length) return `Toutes les rubriques (${all.length})`;
  if (n === 0) return `Aucune rubrique chiffrée (${all.length})`;
  return n === 1
    ? `1 rubrique chiffrée sur ${all.length}`
    : `${n} rubriques chiffrées sur ${all.length}`;
}

// ---------- a consultation read from its documents (25/11) ----------------------------------

export type FactColumn =
  | "title"
  | "buyer_name"
  | "client_address"
  | "site_address"
  | "contact_name"
  | "contact_email"
  | "contact_phone"
  | "reference";

/** The card's fields, in order, with their labels. */
export const FACTS: { column: FactColumn; label: string; long?: boolean }[] = [
  { column: "title", label: "Objet" },
  { column: "buyer_name", label: "Client (qui demande le devis)" },
  { column: "client_address", label: "Adresse du client", long: true },
  { column: "site_address", label: "Adresse du chantier", long: true },
  { column: "contact_name", label: "Contact" },
  { column: "contact_email", label: "E-mail" },
  { column: "contact_phone", label: "Téléphone" },
  { column: "reference", label: "Référence du client" },
];

export type FactRow = {
  column: FactColumn;
  label: string;
  long: boolean;
  value: string;
  /** « lu dans FICHE.pdf, p. 1 », or null when the user typed it. */
  source: string | null;
  /** Empty (or the title Pilao gave until the documents are read): to fill. */
  missing: boolean;
};

type CardBid = Pick<
  Bid,
  "title" | "buyer_name" | "contact_name" | "contact_email" | "reference"
> &
  Pick<
    Bid,
    "client_address" | "site_address" | "contact_phone" | "facts_sources"
  >;

const fileName = (path: string) => path.split("/").pop() ?? path;

export function consultationCard(bid: CardBid): FactRow[] {
  const sources = bid.facts_sources ?? {};
  return FACTS.map(({ column, label, long }) => {
    const value = (bid[column] ?? "").trim();
    const src = sources[column];
    return {
      column,
      label,
      long: !!long,
      value,
      source:
        src?.file && src.page
          ? `lu dans ${fileName(src.file)}, p. ${src.page}`
          : null,
      missing: !value || !!src?.auto,
    };
  });
}

export function missingFacts(rows: FactRow[]): number {
  return rows.filter((r) => r.missing).length;
}

const plural = (n: number, word: string) => `${n} ${word}${n > 1 ? "s" : ""}`;

/** Where the reading of the documents stands, in one sentence. */
export function readingText(read: ConsultationRead): string {
  if (read.status === "reading")
    return "Pilao lit les documents reçus : la fiche se remplit dans une minute environ.";
  if (read.status !== "ready") return read.error ?? "";
  const facts = read.found.length
    ? `Pilao a relevé ${plural(read.found.length, "information")} dans les documents`
    : "Pilao n'a relevé aucune information dans les documents : remplissez la fiche";
  const files = read.price_files;
  if (files.length === 1)
    return `${facts} et trouvé le fichier de prix « ${fileName(files[0].path)} ». Vérifiez-les.`;
  if (files.length > 1)
    return `${facts}. ${files.length} documents de quantités trouvés : choisissez celui à chiffrer dans l'étape Prix.`;
  return `${facts}. Aucun fichier de prix trouvé : indiquez-le dans l'étape Prix.`;
}

/** The price file's download: the DPGF Pilao writes, or the client's own file filled. */
export function downloadLabel(mode: "grid" | "document" | undefined): string {
  return mode === "document"
    ? "Télécharger le DPGF (Excel)"
    : "Télécharger le fichier rempli";
}

export const QUOTE_NUMBER_MAX = 40;

export function quoteNumberError(value: string): string | null {
  return value.trim().length > QUOTE_NUMBER_MAX
    ? `Numéro trop long (${QUOTE_NUMBER_MAX} caractères au plus).`
    : null;
}
