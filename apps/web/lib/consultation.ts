/**
 * Rules of the consultations (ADR-052): a general contractor asks the company for a quote on
 * part of a lot. The dossier is lighter (Aperçu · Documents reçus · Prix · Devis), prices come
 * from « Ma liste de prix » or the company, the quote cites the CCTP. Pure functions.
 */
import type { TabId } from "@/lib/dossier";
import { parseEuros } from "@/lib/format";
import type { BidKind, Inclusion, QuoteState, ServiceIn } from "@/lib/types";

export const KIND_LABELS: Record<BidKind, string> = {
  tender: "Appel d'offres",
  consultation: "Consultation (devis)",
};

export const CONSULTATION_TABS: { id: TabId; label: string }[] = [
  { id: "apercu", label: "Aperçu" },
  { id: "dce", label: "Documents reçus" },
  { id: "prix", label: "Prix" },
  { id: "devis", label: "Devis" },
];

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
