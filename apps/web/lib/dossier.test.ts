import { describe, expect, it } from "vitest";

import {
  blockSummaries,
  daysLeftText,
  defaultTab,
  exportableMemoir,
  overviewTiles,
  shortTitle,
  tabDone,
  tabFromQuery,
  todoItems,
} from "./dossier";
import type { Analysis, Bid, DossierProgress } from "./types";

const NONE: DossierProgress = {
  dce_ready: false,
  analysis_ready: false,
  memoir_ready: false,
  documents_ready: false,
  exported: false,
  blocking_points: 0,
};
const READY: DossierProgress = {
  ...NONE,
  dce_ready: true,
  analysis_ready: true,
};
const NOW = new Date("2026-11-14T10:00:00Z");
const SRC = { file: "RC.pdf", page: 1, dce_file_id: "f" };

function bid(over: Partial<Bid> = {}): Bid {
  return {
    id: "b",
    title: "Entretien des gymnases",
    buyer_name: "Ville de Rillieux-la-Pape",
    reference: "26020M",
    deadline_at: "2026-12-02T11:00:00Z",
    status: "in_progress",
    lot_label: null,
    submitted_amount_cents: null,
    result_rank: null,
    result_notes: null,
    minutes_with_pilao: null,
    minutes_usual: null,
    created_at: "2026-11-14T08:00:00Z",
    progress: READY,
    ...over,
  };
}

type Watch = Analysis["data"] extends infer D
  ? D extends { watch_points: infer W }
    ? W
    : never
  : never;

function analysis(over: {
  watch?: Watch;
  documents?: Analysis["documents"];
  criteria?: { name: string; weight_pct: number }[];
  requirements?: number;
  warnings?: string[];
  visit?: { mandatory: boolean | null; dates: string[] };
  template?: boolean | null;
  questions?: string | null;
  font?: { name: string | null; size: number | null } | null;
  maxPages?: number | null;
  amount?: number | null;
  framework?: string | null;
}): Analysis {
  return {
    id: "a",
    status: "ready",
    error: null,
    dce_version: 1,
    model: null,
    prompt_version: "0.4.0",
    created_at: "2026-11-14T09:00:00Z",
    warnings: over.warnings ?? [],
    requirements: Array.from({ length: over.requirements ?? 0 }, (_, i) => ({
      id: `r${i}`,
      ref: `CCTP-${i + 1}`,
      text: "Exigence",
      category: "other",
      importance: "expected",
      source: SRC,
    })),
    documents: over.documents ?? [],
    go_no_go: {
      score: 60,
      verdict: "to_study",
      factors: [],
      disclaimer: "Avis indicatif",
    },
    framework_amounts: over.framework
      ? {
          minimum_eur_ht: 80000,
          maximum_eur_ht: 170000,
          per_year: true,
          label: over.framework,
          source: SRC,
        }
      : null,
    imposed_font: over.font ?? null,
    data: {
      key_info: {
        buyer_name: { value: "Ville", source: SRC },
        title: { value: "Entretien", source: SRC },
        procedure: { value: "Appel d'offres ouvert", source: SRC },
        estimated_amount_eur_ht:
          over.amount != null ? { value: over.amount, source: SRC } : null,
        duration: { value: "12 mois reconductible 3 fois", source: SRC },
        submission_deadline: null,
        submission_platform: null,
        lots: [],
      },
      site_visit: {
        mandatory: over.visit?.mandatory ?? null,
        dates: over.visit?.dates ?? [],
        details: null,
        source: SRC,
      },
      questions_deadline: over.questions
        ? { value: over.questions, source: SRC }
        : null,
      award_criteria: (over.criteria ?? []).map((c) => ({
        ...c,
        subcriteria: [],
        source: SRC,
      })),
      memoir_requirements: {
        imposed_outline: [],
        response_template_provided: over.template ?? null,
        max_pages: over.maxPages ?? null,
        format_constraints: null,
        source: SRC,
      },
      required_documents: [],
      watch_points: over.watch ?? [],
    },
  };
}

const VISIT_TEXT =
  "Visite obligatoire : l'offre sans attestation de visite signée est déclarée irrégulière.";
const doc = (name: string, status: string, detail = "") => ({
  name,
  phase: "candidature",
  compliance_kind: null,
  status,
  detail,
});

describe("tabs", () => {
  it("opens the DCE until one is deposited, then the overview", () => {
    expect(defaultTab(null)).toBe("dce");
    expect(defaultTab(NONE)).toBe("dce");
    expect(defaultTab({ ...NONE, dce_ready: true })).toBe("apercu");
  });
  it("reads the tab from the address, unknown or empty falls back", () => {
    expect(tabFromQuery("analyse", READY)).toBe("analyse");
    expect(tabFromQuery("xyz", READY)).toBe("apercu");
    expect(tabFromQuery("", NONE)).toBe("dce");
    expect(tabFromQuery(null, READY)).toBe("apercu");
  });
  it("marks each step done from the progress", () => {
    expect(tabDone({ ...READY, memoir_ready: true, exported: true })).toEqual({
      apercu: false,
      dce: true,
      analyse: true,
      memoire: true,
      documents: false,
      export: true,
    });
    expect(tabDone(null).dce).toBe(false);
  });
});

describe("short titles", () => {
  it("cuts a long sentence on a word, keeps a short one", () => {
    const t = shortTitle(VISIT_TEXT);
    expect(t).toBe("Visite obligatoire : l'offre sans attestation de visite…");
    expect(t.length).toBeLessThanOrEqual(61);
    expect(shortTitle("Pondération corrigée")).toBe("Pondération corrigée");
  });
  it("is never empty, even for one giant word", () => {
    expect(shortTitle("")).toBe("Point sans titre");
    expect(shortTitle("   ")).toBe("Point sans titre");
    expect(shortTitle("a".repeat(200))).toBe("a".repeat(60) + "…");
  });
});

const RILLIEUX = analysis({
  watch: [
    {
      text: VISIT_TEXT,
      title: "Visite obligatoire",
      severity: "blocking",
      source: SRC,
    },
    { text: "Lot unique", severity: "warning", source: SRC },
  ],
  visit: { mandatory: true, dates: ["2026-11-20", "2026-11-25"] },
  documents: [
    doc(
      "Attestations fiscales et sociales",
      "expires_before_deadline",
      "Expire le 30/11/2026, avant la date limite de remise.",
    ),
    doc("DC1", "to_prepare"),
  ],
  template: true,
  questions: "2026-11-22T12:00:00+01:00",
});

describe("to-do list", () => {
  it("lists what to do first, in order, each with its tab", () => {
    const { items, more } = todoItems(RILLIEUX, bid(), NOW);
    expect(items.map((i) => [i.level, i.title])).toEqual([
      ["blocking", "Visite obligatoire"],
      ["warning", "Planifier la visite obligatoire"],
      ["warning", "Renouveler : Attestations fiscales et sociales"],
      ["warning", "Écrire le mémoire dans le cadre fourni par l'acheteur"],
      ["info", "Poser vos questions avant le 22/11"],
    ]);
    expect(items[1].detail).toBe("20/11 ou 25/11");
    expect(items[2].detail).toBe(
      "Expire le 30/11/2026, avant la date limite de remise.",
    );
    expect(items[0]).toMatchObject({ tab: "analyse", anchor: "bloc-watch" });
    expect(more).toBe(0);
  });
  it("keeps six lines and counts the rest", () => {
    const watch = Array.from({ length: 8 }, (_, i) => ({
      text: `Point bloquant ${i}`,
      severity: "blocking" as const,
      source: SRC,
    }));
    const { items, more } = todoItems(analysis({ watch }), bid(), NOW);
    expect(items).toHaveLength(6);
    expect(more).toBe(2);
  });
  it("drops the visit once submitted, past questions, and works without analysis", () => {
    const titles = todoItems(
      RILLIEUX,
      bid({ status: "submitted" }),
      NOW,
    ).items.map((i) => i.title);
    expect(titles).not.toContain("Planifier la visite obligatoire");
    const late = new Date("2026-11-23T10:00:00Z");
    expect(
      todoItems(RILLIEUX, bid(), late).items.map((i) => i.title),
    ).not.toContain("Poser vos questions avant le 22/11");
    expect(todoItems(null, bid(), NOW)).toEqual({ items: [], more: 0 });
  });
  it("puts a missing document before one that expires", () => {
    const a = analysis({
      documents: [
        doc("Assurance RC", "expires_before_deadline"),
        doc("Kbis", "missing"),
      ],
    });
    expect(todoItems(a, bid(), NOW).items.map((i) => i.title)).toEqual([
      "Ajouter : Kbis",
      "Renouveler : Assurance RC",
    ]);
  });
});

describe("overview tiles", () => {
  it("shows the opinion, the amount, the deadline and the visit", () => {
    const tiles = overviewTiles(
      analysis({
        framework: "De 80 000 € à 170 000 € HT par an",
        visit: { mandatory: true, dates: [] },
      }),
      bid(),
      NOW,
    );
    expect(tiles.map((t) => t.label)).toEqual([
      "Avis Go / No-Go",
      "Montant",
      "Date limite",
      "Visite du site",
    ]);
    expect(tiles[0]).toMatchObject({
      value: "À étudier · 60/100",
      tone: "warning",
    });
    expect(tiles[1].value).toBe("De 80 000 € à 170 000 € HT par an");
    expect(tiles[2].sub).toBe("dans 18 jours");
    expect(tiles[3]).toMatchObject({ value: "Obligatoire", tone: "danger" });
  });
  it("prefers an estimated amount, says when there is none", () => {
    expect(
      overviewTiles(analysis({ amount: 120000 }), bid(), NOW)[1].value,
    ).toBe("120 000 € HT");
    expect(overviewTiles(analysis({}), bid(), NOW)[1].value).toBe(
      "Non indiqué",
    );
  });
  it("turns red two days before the deadline", () => {
    const soon = bid({ deadline_at: "2026-11-16T11:00:00Z" });
    expect(overviewTiles(analysis({}), soon, NOW)[2]).toMatchObject({
      sub: "dans 2 jours",
      tone: "danger",
    });
  });
  it("waits for the analysis without failing", () => {
    const tiles = overviewTiles(null, bid(), NOW);
    expect(tiles[0].value).toBe("Analyse en cours");
    expect(tiles[3].value).toBe("Analyse en cours");
    expect(tiles[2].sub).toBe("dans 18 jours");
  });
});

describe("block summaries", () => {
  it("says the essential in one line per block", () => {
    const s = blockSummaries(
      analysis({
        criteria: [
          { name: "Valeur technique", weight_pct: 50 },
          { name: "Prix", weight_pct: 40 },
          { name: "Développement durable", weight_pct: 10 },
        ],
        documents: [
          doc("Attestations", "expires_before_deadline"),
          ...Array.from({ length: 6 }, (_, i) =>
            doc(`Pièce ${i}`, "to_prepare"),
          ),
        ],
        watch: [
          { text: "a", severity: "blocking", source: SRC },
          ...Array.from({ length: 4 }, () => ({
            text: "b",
            severity: "warning" as const,
            source: SRC,
          })),
          { text: "c", severity: "info", source: SRC },
        ],
        requirements: 45,
        warnings: ["x", "y", "z"],
        maxPages: 10,
        font: { name: "Times New Roman", size: 11 },
        template: true,
      }),
    );
    expect(s.gonogo.text).toBe("À étudier · 60/100");
    expect(s.key.text).toBe(
      "Appel d'offres ouvert · 12 mois reconductible 3 fois",
    );
    expect(s.criteria.text).toBe(
      "Valeur technique 50 % · Prix 40 % · Développement durable 10 %",
    );
    expect(s.documents.badges).toEqual([
      { label: "1 à renouveler", tone: "warning" },
      { label: "6 à préparer", tone: "neutral" },
    ]);
    expect(s.watch.badges).toEqual([
      { label: "1 bloquant", tone: "blocking" },
      { label: "4 attention", tone: "warning" },
      { label: "1 à noter", tone: "info" },
    ]);
    expect(s.requirements.text).toBe("45 exigences");
    expect(s.memoir.text).toBe(
      "10 pages · Times New Roman 11 · cadre de l'acheteur",
    );
    expect(s.checks.text).toBe("3 points à vérifier");
  });
  it("never leaves a summary empty", () => {
    const s = blockSummaries(analysis({ warnings: ["x"] }));
    expect(s.criteria.text).toBe("Aucun critère trouvé");
    expect(s.requirements.text).toBe("Aucune exigence trouvée");
    expect(s.documents.text).toBe("Aucune pièce trouvée");
    expect(s.watch.text).toBe("Aucun point de vigilance");
    expect(s.memoir.text).toBe("Pas de consigne trouvée");
    expect(s.checks.text).toBe("1 point à vérifier");
  });
});

describe("days left", () => {
  it("counts calendar days in Paris", () => {
    expect(daysLeftText("2026-12-02T11:00:00Z", NOW)).toBe("dans 18 jours");
    expect(daysLeftText("2026-11-15T08:00:00Z", NOW)).toBe("demain");
    expect(daysLeftText("2026-11-14T20:00:00Z", NOW)).toBe("aujourd'hui");
    expect(daysLeftText("2026-11-10T08:00:00Z", NOW)).toBe("date dépassée");
  });
});

describe("final review fixes", () => {
  it("keeps a visit date that is not a calendar date as written (never crashes)", () => {
    const a = analysis({
      visit: { mandatory: true, dates: ["20/11/2026", "sur rendez-vous"] },
    });
    const visit = todoItems(a, bid(), NOW).items.find(
      (i) => i.title === "Planifier la visite obligatoire",
    );
    expect(visit?.detail).toBe("20/11/2026 ou sur rendez-vous");
    expect(overviewTiles(a, bid(), NOW)[3].sub).toBe(
      "20/11/2026 ou sur rendez-vous",
    );
    const q = analysis({ questions: "avant le 22 novembre" });
    expect(() => todoItems(q, bid(), NOW)).not.toThrow();
  });
  it("says when the analysis failed or waits for credits", () => {
    const failed = { ...analysis({}), status: "error" };
    const waiting = { ...analysis({}), status: "waiting_credits" };
    expect(overviewTiles(failed, bid(), NOW)[0].value).toBe("Analyse en échec");
    expect(overviewTiles(waiting, bid(), NOW)[0].value).toBe(
      "En attente de crédits",
    );
    expect(overviewTiles(failed, bid(), NOW)[3].value).toBe("Analyse en échec");
  });
  it("exports the latest drafted memoir when a new draft was started", () => {
    const v = (version: number, status: string) => ({
      id: `m${version}`,
      version,
      status,
      created_at: "2026-11-14T09:00:00Z",
      chapters: 2,
      drafted: 2,
    });
    expect(exportableMemoir([v(2, "draft"), v(1, "ready")])).toEqual(
      v(1, "ready"),
    );
    expect(exportableMemoir([v(3, "exported"), v(2, "ready")])).toEqual(
      v(3, "exported"),
    );
    expect(exportableMemoir([v(1, "draft")])).toBeNull();
    expect(exportableMemoir([])).toBeNull();
  });
});
