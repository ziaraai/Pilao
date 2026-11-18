import { describe, expect, it } from "vitest";

import {
  KIND_LABELS,
  chosenLabel,
  excludedFromChosen,
  sectionsOf,
  PRICE_UNITS,
  inclusionSource,
  quoteAction,
  serviceErrors,
  servicesFromRows,
  toggleSection,
  vatLabel,
} from "@/lib/consultation";
import { tabDone, tabFromQuery, tabsFor } from "@/lib/dossier";
import type { DossierProgress, QuoteState } from "@/lib/types";

const READY: DossierProgress = {
  dce_ready: true,
  analysis_ready: false,
  memoir_ready: false,
  documents_ready: false,
  exported: false,
  blocking_points: 0,
};

describe("the tabs of a dossier", () => {
  it("are the light ones in a consultation", () => {
    expect(tabsFor("consultation").map((t) => t.label)).toEqual([
      "Aperçu",
      "Documents reçus",
      "Prix",
      "Devis",
    ]);
    expect(tabsFor("tender").map((t) => t.id)).toEqual([
      "apercu",
      "dce",
      "analyse",
      "memoire",
      "prix",
      "documents",
      "export",
    ]);
  });

  it("never open a tab the dossier has not", () => {
    expect(tabFromQuery("devis", READY, "consultation")).toBe("devis");
    expect(tabFromQuery("memoire", READY, "consultation")).toBe("apercu");
    expect(tabFromQuery("devis", READY, "tender")).toBe("apercu");
    expect(tabFromQuery("devis", READY)).toBe("apercu");
  });

  it("mark the quote done when it is ready", () => {
    expect(tabDone(READY, true).devis).toBe(true);
    expect(tabDone(READY).devis).toBe(false);
  });

  it("name the two kinds", () => {
    expect(KIND_LABELS.consultation).toBe("Consultation (devis)");
    expect(KIND_LABELS.tender).toBe("Appel d'offres");
  });
});

describe("a rubrique taken back or set aside", () => {
  it("leaves the others as they were", () => {
    expect(toggleSection(["a", "b"], "a", true)).toEqual(["b"]);
    expect(toggleSection(["b"], "a", false)).toEqual(["b", "a"]);
    expect(toggleSection(["b"], "b", false)).toEqual(["b"]);
  });
});

describe("« Ma liste de prix »", () => {
  it("offers the server's units", () => {
    expect(PRICE_UNITS).toEqual([
      "m²",
      "ml",
      "m³",
      "heure",
      "jour",
      "forfait",
      "u",
      "passage",
      "mois",
    ]);
  });

  it("turns the rows typed into the list saved, blank rows dropped", () => {
    const rows = [
      {
        name: " Nettoyage avant OPR ",
        unit: "m²",
        price: "1,50",
        description: "",
      },
      { name: "", unit: "m²", price: "", description: "" },
      { name: "Vitrerie", unit: "m²", price: "2", description: " 2 faces " },
    ];
    expect(serviceErrors(rows)).toEqual({});
    expect(servicesFromRows(rows)).toEqual([
      {
        name: "Nettoyage avant OPR",
        unit: "m²",
        price_cents: 150,
        description: null,
      },
      {
        name: "Vitrerie",
        unit: "m²",
        price_cents: 200,
        description: "2 faces",
      },
    ]);
  });

  it("says which row is wrong", () => {
    const rows = [
      { name: "Nettoyage", unit: "m²", price: "abc", description: "" },
      { name: "", unit: "m²", price: "3", description: "" },
    ];
    expect(serviceErrors(rows)).toEqual({
      0: "Prix invalide (ex. : 1,50).",
      1: "Nom de la prestation manquant.",
    });
  });
});

describe("the quote", () => {
  it("writes the VAT rate the French way", () => {
    expect(vatLabel(2000)).toBe("20 %");
    expect(vatLabel(550)).toBe("5,5 %");
    expect(vatLabel(1000)).toBe("10 %");
  });

  it("cites the CCTP page of a bullet, or says the company wrote it", () => {
    expect(inclusionSource({ text: "x", file: "CCTP.pdf", page: 41 })).toBe(
      "CCTP.pdf, p. 41",
    );
    expect(inclusionSource({ text: "x", file: null, page: null })).toBe(
      "ajoutée par vous",
    );
  });

  it("offers the right button", () => {
    const state = (over: Partial<QuoteState>): QuoteState => ({
      quote: null,
      blocking: null,
      cctp: true,
      ...over,
    });
    expect(quoteAction(state({ blocking: "Il reste 2 prix" }))).toBe("blocked");
    expect(quoteAction(state({}))).toBe("prepare_paid");
    expect(quoteAction(state({ cctp: false }))).toBe("prepare_free");
    const quote = {
      id: "q",
      number: "D-2026-0001",
      status: "ready" as const,
      error: null,
      inclusions: [],
      validity_days: 30,
      vat_bp: 2000,
      total_ht_cents: 100,
      vat_cents: 20,
      total_ttc_cents: 120,
      options_total_cents: 0,
      has_pdf: true,
      has_docx: true,
      stale: false,
      updated_at: "2026-11-17T10:00:00Z",
    };
    expect(quoteAction(state({ quote }))).toBe("ready");
    expect(
      quoteAction(state({ quote: { ...quote, status: "drafting" } })),
    ).toBe("drafting");
  });
});

describe("the rubriques you price, chosen in one list", () => {
  const lines = [
    { section: "Travaux sur ouvrages existants" },
    { section: "Travaux sur ouvrages existants" },
    { section: "" },
    { section: "Nettoyages" },
    { section: "Peintures" },
  ];

  it("lists each rubrique once, in the file's order", () => {
    expect(sectionsOf(lines)).toEqual([
      "Travaux sur ouvrages existants",
      "Nettoyages",
      "Peintures",
    ]);
  });

  it("sets aside every rubrique not chosen", () => {
    const all = sectionsOf(lines);
    expect(excludedFromChosen(all, ["Nettoyages"])).toEqual([
      "Travaux sur ouvrages existants",
      "Peintures",
    ]);
    expect(excludedFromChosen(all, all)).toEqual([]);
  });

  it("says how many are priced on the button", () => {
    expect(chosenLabel(["a", "b", "c"], ["a", "c"])).toBe(
      "1 rubrique chiffrée sur 3",
    );
    expect(chosenLabel(["a", "b", "c"], [])).toBe("Toutes les rubriques (3)");
    expect(chosenLabel(["a", "b", "c"], ["a"])).toBe(
      "2 rubriques chiffrées sur 3",
    );
  });
});
