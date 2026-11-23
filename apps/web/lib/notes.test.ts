import { describe, expect, it } from "vitest";

import { analysisNotes } from "@/lib/notes";
import { analysis, SRC } from "@/lib/test-fixtures";

const NOW = new Date("2026-11-14T10:00:00Z");
const pairs = (a: ReturnType<typeof analysis>) =>
  analysisNotes(a, NOW).map((n) => `${n.label} : ${n.text}`);

describe("the analysis as short notes", () => {
  it("says the essentials in one line each, in reading order", () => {
    const a = analysis({
      criteria: [
        { name: "Valeur technique", weight_pct: 60 },
        { name: "Prix", weight_pct: 40 },
      ],
      visit: { mandatory: true, dates: ["28/11"] },
      questions: "2026-11-27T11:00:00Z",
      maxPages: 20,
      amount: 180000,
    });
    a.data!.key_info.submission_deadline = {
      value: "2026-12-05T11:00:00Z",
      source: SRC,
    };
    a.data!.key_info.submission_platform = { value: "PLACE", source: SRC };
    expect(pairs(a)).toEqual([
      "Avis : À étudier (60/100)",
      "Objet : Entretien",
      "Montant : 180 000 € HT",
      "Durée : 12 mois reconductible 3 fois",
      "Date limite : 5 décembre 2026 à 12:00 (dans 21 jours) · dépôt sur PLACE",
      "Visite : Obligatoire · 28/11",
      "Questions : jusqu'au 27 novembre 2026 à 12:00",
      "Critères : Valeur technique 60 % · Prix 40 %",
      "Mémoire : 20 pages",
    ]);
  });

  it("keeps the source of every note taken from the DCE", () => {
    const notes = analysisNotes(analysis({ amount: 1000 }), NOW);
    expect(notes.find((n) => n.label === "Montant")?.source).toEqual(SRC);
    expect(notes.find((n) => n.label === "Avis")?.source).toBeNull(); // Pilao's own reading
  });

  it("lists each blocking or attention point, and counts the ones only to note", () => {
    const a = analysis({
      watch: [
        {
          text: "Visite obligatoire sous peine de rejet",
          title: "Visite obligatoire",
          severity: "blocking",
          source: SRC,
        },
        {
          text: "Lot unique pour trois sites éloignés",
          severity: "warning",
          source: SRC,
        },
        { text: "Variante interdite", severity: "info", source: SRC },
        { text: "Paiement à 30 jours", severity: "info", source: SRC },
      ],
    });
    const watch = analysisNotes(a, NOW).filter((n) =>
      ["Bloquant", "Attention", "À noter"].includes(n.label),
    );
    expect(watch.map((n) => [n.label, n.text, n.tone])).toEqual([
      ["Bloquant", "Visite obligatoire", "danger"],
      ["Attention", "Lot unique pour trois sites éloignés", "warning"],
      ["À noter", "2 autres points dans le détail", "info"],
    ]);
  });

  it("sums up the documents to provide, the missing ones first", () => {
    const doc = (status: string) => ({
      name: "Kbis",
      phase: "candidature",
      compliance_kind: null,
      status,
      detail: "",
    });
    const a = analysis({
      documents: [doc("missing"), doc("expired"), doc("available")],
    });
    expect(
      analysisNotes(a, NOW).find((n) => n.label === "Pièces"),
    ).toMatchObject({
      text: "3 pièces demandées · 1 manquante · 1 à renouveler",
      tone: "danger",
    });
  });

  it("never breaks on a date written in words", () => {
    const a = analysis({ questions: "sur rendez-vous" });
    expect(pairs(a)).toContain("Questions : sur rendez-vous");
  });
});
