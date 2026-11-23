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

/** Lower case, without accents: the rules below read the words, not their spelling. */
function plainWords(text: string): string {
  return text
    .normalize("NFD")
    .replace(/[\u0300-\u036f]/g, "")
    .replace(/[’']/g, " ")
    .toLowerCase();
}

/** Words that tie a missing item to this tender: the profile cannot answer it. */
const ABOUT_THIS_TENDER = [
  "ce marche",
  "du marche",
  "cette consultation",
  "ce site",
  "chaque batiment",
  "chaque site",
  "par batiment",
  "par site",
  "affecte",
  "affectation",
  "designe",
  "volume horaire",
  "planning",
];

/**
 * The item is answered in this dossier (« Répondre » first), not in the profile: a detail of
 * the tender, or a company's datum asked for this tender (the staff per building, the team
 * leader named for it…), which the profile's lists cannot hold.
 */
export function answersHere(item: MissingItem): boolean {
  if (!isCompanyKind(item.kind)) return true;
  const words = plainWords(item.text);
  return ABOUT_THIS_TENDER.some((w) => words.includes(w));
}

/** Example answers, in grey in the answer box: the first family whose words match. */
const EXAMPLES: { words: string[][]; example: string }[] = [
  {
    words: [["sante au travail"], ["medecine du travail"]],
    example: "ex. AST Grand Lyon, visite tous les 2 ans",
  },
  {
    words: [["vitr"]],
    example:
      "ex. perches télescopiques, raclettes et mouilleurs, nettoyant vitres ; nacelle louée pour les vitrages en hauteur",
  },
  {
    words: [
      ["chef d equipe"],
      ["encadr"],
      ["responsable"],
      ["referent"],
      ["interlocuteur"],
    ],
    example:
      "ex. M. Martin, chef d'équipe, 10 ans d'expérience, 06 12 34 56 78",
  },
  {
    words: [
      ["effectif", "horaire"],
      ["effectif", "heure"],
      ["agent", "horaire"],
      ["agent", "heure"],
    ],
    example:
      "ex. Hôtel de ville : 2 agents, 15 h / semaine ; gymnase : 1 agent, 8 h / semaine",
  },
  {
    words: [
      ["materiel"],
      ["machine"],
      ["autolaveuse"],
      ["monobrosse"],
      ["equipement"],
    ],
    example:
      "ex. Bâtiment A : 1 autolaveuse Nilfisk SC351 ; bâtiment B : 1 monobrosse, 2 chariots de ménage",
  },
  {
    words: [["produit"]],
    example:
      "ex. produits écolabellisés (Ecolabel européen), dosés par une centrale de dilution",
  },
  {
    words: [["planning"], ["plage"], ["horaire"], ["frequence"], ["passage"]],
    example:
      "ex. du lundi au vendredi, de 6 h à 8 h ; vitrerie une fois par trimestre",
  },
  {
    words: [["formation"], ["habilitation"], ["caces"], ["qualification"]],
    example:
      "ex. CQP Agent de propreté, habilitation travail en hauteur, CACES nacelle",
  },
  {
    words: [["remplacement"], ["absence"], ["astreinte"], ["continuite"]],
    example: "ex. agent absent remplacé sous 24 h, astreinte joignable 7 j / 7",
  },
  {
    words: [["effectif"], ["agent"], ["personnel"], ["salarie"]],
    example: "ex. 4 agents, dont 1 chef d'équipe",
  },
  {
    words: [["chiffre d affaires"]],
    example: "ex. 2023 : 850 000 € HT ; 2024 : 920 000 € HT",
  },
  {
    words: [["certification"], ["iso"], ["qualipropre"], ["label"]],
    example: "ex. Qualipropre n° 1234, valable jusqu'au 31/12/2027",
  },
  {
    words: [["reference"], ["marche similaire"], ["marches similaires"]],
    example:
      "ex. Ville de Montbrison, nettoyage des écoles, 2022-2025, 85 000 € HT / an",
  },
  {
    words: [["surface"], ["m2"], ["m²"]],
    example: "ex. 1 200 m² de bureaux, 300 m² de sanitaires",
  },
];

/** The example shown in grey in the answer box (never written into the memoir). */
export function answerExample(text: string): string {
  const words = plainWords(text);
  const found = EXAMPLES.find((f) =>
    f.words.some((all) => all.every((w) => words.includes(w))),
  );
  return found?.example ?? "Votre réponse, en quelques mots ou chiffres";
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
