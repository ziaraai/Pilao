import { describe, expect, it } from "vitest";

import {
  KIND_LABELS,
  chosenLabel,
  consultationCard,
  downloadLabel,
  excludedFromChosen,
  missingFacts,
  quoteNumberError,
  readingText,
  sectionsOf,
  PRICE_UNITS,
  inclusionSource,
  quoteAction,
  serviceErrors,
  servicesFromRows,
  toggleSection,
  vatLabel,
} from "@/lib/consultation";
import type { ConsultationRead, QuoteState } from "@/lib/types";

describe("a consultation", () => {
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

describe("the consultation's card read in its documents (25/11)", () => {
  const bid = {
    title: "Consultation du 25/11/2026",
    buyer_name: "CCTB",
    client_address: null,
    site_address: "M. DELBARRE Jean, 7 rue du Général Leclerc",
    contact_name: null,
    contact_email: null,
    contact_phone: "04 77 25 05 44",
    reference: "DE36594",
    facts_sources: {
      title: { auto: true },
      buyer_name: { file: "FICHE.pdf", page: 1 },
      site_address: { file: "DCE/FICHE.pdf", page: 2 },
    },
  };

  it("shows each fact with where it was read, the empty ones to fill", () => {
    const rows = consultationCard(bid);
    expect(rows.map((r) => r.column)).toEqual([
      "title",
      "buyer_name",
      "client_address",
      "site_address",
      "contact_name",
      "contact_email",
      "contact_phone",
      "reference",
    ]);
    const by = Object.fromEntries(rows.map((r) => [r.column, r]));
    expect(by.buyer_name.source).toBe("lu dans FICHE.pdf, p. 1");
    expect(by.site_address.source).toBe("lu dans FICHE.pdf, p. 2");
    expect(by.contact_phone.source).toBeNull(); // typed by the user
    expect(by.client_address.missing && !by.buyer_name.missing).toBe(true);
    // the title Pilao gave until the documents are read is still to fill
    expect(by.title.missing).toBe(true);
    expect(by.title.value).toBe("Consultation du 25/11/2026");
  });

  it("counts what is left to fill", () => {
    expect(missingFacts(consultationCard(bid))).toBe(4);
  });
});

describe("the reading of the documents", () => {
  it("says where it stands", () => {
    expect(readingText({ status: "reading" } as ConsultationRead)).toMatch(
      /Pilao lit les documents/,
    );
    expect(
      readingText({
        status: "ready",
        found: ["title", "client_name"],
        price_files: [{ dce_file_id: "1", path: "FICHE.pdf", reason: "" }],
      } as ConsultationRead),
    ).toBe(
      "Pilao a relevé 2 informations dans les documents et trouvé le fichier de prix « FICHE.pdf ». Vérifiez-les.",
    );
    expect(
      readingText({
        status: "ready",
        found: [],
        price_files: [
          { dce_file_id: "1", path: "DCE/FICHE.pdf", reason: "" },
          { dce_file_id: "2", path: "METRE.pdf", reason: "" },
        ],
      } as unknown as ConsultationRead),
    ).toBe(
      "Pilao n'a relevé aucune information dans les documents : remplissez la fiche. 2 documents de quantités trouvés : choisissez celui à chiffrer dans l'étape Prix.",
    );
    expect(
      readingText({
        status: "ready",
        found: ["reference"],
        price_files: [],
      } as unknown as ConsultationRead),
    ).toBe(
      "Pilao a relevé 1 information dans les documents. Aucun fichier de prix trouvé : indiquez-le dans l'étape Prix.",
    );
  });
});

describe("the price file's download", () => {
  it("names a DPGF written by Pilao, or the client's own file filled", () => {
    expect(downloadLabel("document")).toBe("Télécharger le DPGF (Excel)");
    expect(downloadLabel("grid")).toBe("Télécharger le fichier rempli");
  });
});

describe("the quote's number", () => {
  it("is free, up to 40 characters", () => {
    expect(quoteNumberError("")).toBeNull();
    expect(quoteNumberError(" DEV-2026-118 ")).toBeNull();
    expect(quoteNumberError("x".repeat(41))).toBe(
      "Numéro trop long (40 caractères au plus).",
    );
  });
});
