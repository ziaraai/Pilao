import { describe, expect, it } from "vitest";

import { guideSteps, nextStep, stepFromQuery } from "@/lib/guide";
import type { Bid, DossierProgress, QuoteState } from "@/lib/types";

const NONE: DossierProgress = {
  dce_ready: false,
  analysis_ready: false,
  memoir_ready: false,
  documents_ready: false,
  exported: false,
  blocking_points: 0,
  missing_count: 0,
  price_files: 0,
  prices_ready: false,
};

function bid(progress: Partial<DossierProgress>, over: Partial<Bid> = {}): Bid {
  return {
    id: "b1",
    kind: "tender",
    contact_name: null,
    contact_email: null,
    title: "Nettoyage des bâtiments communaux",
    buyer_name: "Ville de Montbrison",
    reference: null,
    deadline_at: "2026-12-05T11:00:00Z",
    status: "in_progress",
    lot_label: null,
    submitted_amount_cents: null,
    result_rank: null,
    result_notes: null,
    minutes_with_pilao: null,
    minutes_usual: null,
    created_at: "2026-11-20T10:00:00Z",
    progress: { ...NONE, ...progress },
    ...over,
  };
}

const ids = (b: Bid, q?: QuoteState | null) =>
  guideSteps(b, q).map((s) => `${s.id}:${s.state}`);

describe("the steps of a tender", () => {
  it("start at the DCE, without « Prix » while no price file is known", () => {
    expect(ids(bid({}))).toEqual([
      "dce:current",
      "analyse:todo",
      "memoire:todo",
      "documents:todo",
      "export:todo",
    ]);
  });

  it("show « Prix » once the DCE holds a price file", () => {
    const b = bid({ dce_ready: true, analysis_ready: true, price_files: 1 });
    expect(ids(b)).toEqual([
      "dce:done",
      "analyse:done",
      "memoire:current",
      "prix:todo",
      "documents:todo",
      "export:todo",
    ]);
  });

  it("keep the memoir current while information is missing", () => {
    const b = bid({
      dce_ready: true,
      analysis_ready: true,
      memoir_ready: true,
      missing_count: 3,
    });
    const memoir = guideSteps(b).find((s) => s.id === "memoire");
    expect(memoir).toMatchObject({
      state: "current",
      note: "3 informations à compléter",
    });
  });

  it("flag the analysis when it found a blocking point", () => {
    const b = bid({
      dce_ready: true,
      analysis_ready: true,
      blocking_points: 2,
    });
    expect(guideSteps(b).find((s) => s.id === "analyse")).toMatchObject({
      state: "done",
      alert: true,
      note: "2 points bloquants",
    });
  });

  it("name the last step « Envoi », done once the offer is deposited", () => {
    const all = {
      dce_ready: true,
      analysis_ready: true,
      memoir_ready: true,
      documents_ready: true,
      exported: true,
    };
    expect(guideSteps(bid(all)).at(-1)).toMatchObject({
      label: "Envoi",
      state: "current",
      note: "à déposer",
    });
    const sent = guideSteps(bid(all, { status: "submitted" }));
    expect(sent.every((s) => s.state === "done")).toBe(true);
  });
});

describe("the next step of a tender", () => {
  it("asks for the DCE first", () => {
    expect(nextStep(bid({}))).toMatchObject({
      id: "dce",
      index: 1,
      total: 5,
      title: "Récupérer le DCE",
      action: "Récupérer le DCE",
    });
  });

  it("says when the analysis waits for credits or failed", () => {
    const b = bid({ dce_ready: true });
    expect(nextStep(b, null, null, "waiting_credits")).toMatchObject({
      id: "analyse",
      title: "Lancer l'analyse du DCE",
      action: "Ouvrir l'analyse",
    });
    expect(nextStep(b, null, null, "error")).toMatchObject({
      id: "analyse",
      title: "Relancer l'analyse du DCE",
      action: "Ouvrir l'analyse",
    });
    expect(nextStep(b, null, null, "processing")).toMatchObject({
      title: "Lire l'analyse du DCE",
    });
  });

  it("asks for the missing information by its number", () => {
    const b = bid({
      dce_ready: true,
      analysis_ready: true,
      memoir_ready: true,
      missing_count: 1,
      price_files: 1,
    });
    expect(nextStep(b)).toMatchObject({
      id: "memoire",
      index: 3,
      total: 6,
      title: "Compléter 1 information pour le mémoire",
      action: "Compléter maintenant",
      anchor: "bloc-missing",
    });
  });

  it("asks to fill the price file before the documents", () => {
    const b = bid({
      dce_ready: true,
      analysis_ready: true,
      memoir_ready: true,
      price_files: 1,
    });
    expect(nextStep(b)).toMatchObject({
      id: "prix",
      title: "Remplir le bordereau de prix",
    });
  });

  it("reminds that Pilao never deposits the offer, with the platform and the deadline", () => {
    const b = bid({
      dce_ready: true,
      analysis_ready: true,
      memoir_ready: true,
      documents_ready: true,
    });
    const next = nextStep(b, null, "PLACE");
    expect(next).toMatchObject({
      id: "export",
      title: "Télécharger le dossier complet",
    });
    expect(next.text).toContain(
      "déposez-le vous-même sur PLACE avant le 5 décembre 2026",
    );
    expect(next.text).toContain("Pilao ne dépose jamais à votre place");
  });

  it("asks to confirm the deposit once the dossier is exported", () => {
    const b = bid({
      dce_ready: true,
      analysis_ready: true,
      memoir_ready: true,
      documents_ready: true,
      exported: true,
    });
    expect(nextStep(b)).toMatchObject({
      id: "export",
      title: "Déposer votre offre",
      action: "J'ai déposé mon offre",
      deposit: true,
    });
  });

  it("asks for the result after the deposit, and says when the dossier is over", () => {
    const done = { dce_ready: true, analysis_ready: true, memoir_ready: true };
    expect(nextStep(bid(done, { status: "submitted" }))).toMatchObject({
      title: "Noter le résultat",
      action: "Indiquer le résultat",
      result: true, // the card asks « gagné » or « perdu » in one click
    });
    // deposited without Pilao's documents: nothing is pushed as « current » any more
    expect(ids(bid(done, { status: "submitted" }))).not.toContain(
      "documents:current",
    );
    expect(nextStep(bid(done, { status: "won" }))).toMatchObject({
      title: "Marché gagné",
      action: null,
    });
    expect(nextStep(bid({}, { status: "dropped" }))).toMatchObject({
      title: "Réponse abandonnée",
      action: null,
    });
  });
});

describe("a consultation", () => {
  const consult = (p: Partial<DossierProgress>, over: Partial<Bid> = {}) =>
    bid(p, { kind: "consultation", ...over });
  const quote = (over: Partial<QuoteState>): QuoteState => ({
    quote: null,
    blocking: null,
    cctp: true,
    ...over,
  });

  it("has its three light steps", () => {
    expect(ids(consult({}), null)).toEqual([
      "dce:current",
      "prix:todo",
      "devis:todo",
    ]);
    expect(guideSteps(consult({}), null).map((s) => s.label)).toEqual([
      "Documents reçus",
      "Prix",
      "Devis",
    ]);
  });

  it("passes the server's reason when prices are missing", () => {
    const q = quote({
      blocking: "Il reste 2 prix à saisir dans l'onglet Prix.",
    });
    expect(nextStep(consult({ dce_ready: true }), q)).toMatchObject({
      id: "prix",
      title: "Remplir le fichier de prix",
      text: "Il reste 2 prix à saisir.",
    });
  });

  it("asks to prepare, then to send the quote", () => {
    expect(nextStep(consult({ dce_ready: true }), quote({}))).toMatchObject({
      id: "devis",
      title: "Préparer le devis",
    });
    const ready = quote({
      quote: { status: "ready", number: "D-2026-0001" } as QuoteState["quote"],
    });
    expect(nextStep(consult({ dce_ready: true }), ready)).toMatchObject({
      id: "devis",
      title: "Relire puis envoyer le devis",
      deposit: true,
    });
  });
});

describe("the step opened from the address (?onglet=…)", () => {
  it("opens a step the dossier has, nothing otherwise", () => {
    const steps = guideSteps(bid({ dce_ready: true }));
    expect(stepFromQuery("analyse", steps)).toBe("analyse");
    expect(stepFromQuery("prix", steps)).toBeNull(); // no price file in this DCE
    expect(stepFromQuery("apercu", steps)).toBeNull(); // the old overview is the page itself
    expect(stepFromQuery("", steps)).toBeNull();
    expect(stepFromQuery(null, steps)).toBeNull();
    const consult = guideSteps(bid({}, { kind: "consultation" }), null);
    expect(stepFromQuery("devis", consult)).toBe("devis");
    expect(stepFromQuery("memoire", consult)).toBeNull();
  });
});
