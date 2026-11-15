/**
 * « Ce qu'il manque » (ADR-048): the words and the drawers of the missing items of a dossier.
 * Each item belongs to a drawer of the profile; a company's datum is added there (and serves
 * every dossier), a detail of the tender is answered in place.
 */
import type { MissingItem, MissingKind, ProfileGaps } from "@/lib/types";

export type KindMeta = {
  icon: string;
  /** The button that opens the drawer's form; ``null``: answered in place. */
  button: string | null;
  /** The profile's tab (``/profil?onglet=…``). */
  profileSection: string | null;
};

export const KIND_META: Record<MissingKind, KindMeta> = {
  staff: {
    icon: "👥",
    button: "Ajouter dans Moyens humains",
    profileSection: "moyens",
  },
  equipment: {
    icon: "🧰",
    button: "Ajouter dans Moyens matériels",
    profileSection: "moyens",
  },
  certification: {
    icon: "📜",
    button: "Ajouter dans Certifications",
    profileSection: "certifications",
  },
  reference: {
    icon: "📁",
    button: "Ajouter dans Références",
    profileSection: "references",
  },
  identity: {
    icon: "🆔",
    button: "Compléter mon profil",
    profileSection: "identite",
  },
  tender: { icon: "✏️", button: null, profileSection: null },
};

export function isCompanyKind(kind: MissingKind): boolean {
  return kind !== "tender";
}

function informations(n: number): string {
  return `${n} information${n > 1 ? "s" : ""}`;
}

export function missingTitle(n: number): string {
  return `Ce qu'il manque : ${informations(n)}`;
}

export function missingSummary(n: number): string {
  return `${informations(n)} à compléter`;
}

export function chaptersLabel(n: number): string {
  return `dans ${n} chapitre${n > 1 ? "s" : ""}`;
}

export const NOT_ENOUGH =
  "La donnée ajoutée ne suffit pas pour cette phrase : précisez-la ou répondez directement.";

export function fillMessage(item: MissingItem): string | null {
  const fill = item.fill;
  if (!fill) return null;
  if (fill.status === "pending" || fill.status === "running")
    return "Complétion en cours…";
  if (fill.status === "error")
    return fill.error ?? "La complétion n'a pas abouti : réessayez.";
  return fill.outcome === "not_enough" ? NOT_ENOUGH : null;
}

const GAPS: { key: keyof ProfileGaps; what: string }[] = [
  { key: "staff", what: "moyens humains" },
  { key: "equipment", what: "matériel" },
  { key: "references", what: "références" },
];

export function gapMessages(
  gaps: ProfileGaps,
): { key: keyof ProfileGaps; text: string }[] {
  return GAPS.filter((g) => gaps[g.key]).map((g) => ({
    key: g.key,
    text: `Votre profil n'a pas de ${g.what} : le mémoire aura des trous.`,
  }));
}

/** The first lines of the add-to-profile window; ``null``: opened before the drafting
 * (« Avant la rédaction »), with no marker and no sentence to complete yet. */
export function dialogIntro(markerText: string | null): string {
  const where =
    "Ce que vous ajoutez est enregistré dans votre profil et servira à tous vos dossiers";
  return markerText
    ? `Il manque : ${markerText}. ${where} ; Pilao complète ensuite les phrases concernées.`
    : `${where}.`;
}
