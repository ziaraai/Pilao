import { describe, expect, it } from "vitest";

import {
  KIND_META,
  answerExample,
  answersHere,
  chaptersLabel,
  dialogIntro,
  fillMessage,
  gapMessages,
  isCompanyKind,
  missingSummary,
  missingTitle,
} from "@/lib/missing";
import type { MissingItem } from "@/lib/types";

function item(over: Partial<MissingItem> = {}): MissingItem {
  return {
    key: "nombre d agents",
    text: "nombre d'agents",
    kind: "staff",
    sections: [{ id: "s1", title: "1. Moyens" }],
    documents: [],
    fill: null,
    ...over,
  };
}

describe("« Ce qu'il manque »", () => {
  it("counts in words", () => {
    expect(missingTitle(1)).toBe("Ce qu'il manque : 1 information");
    expect(missingTitle(5)).toBe("Ce qu'il manque : 5 informations");
    expect(missingSummary(1)).toBe("1 information à compléter");
    expect(missingSummary(3)).toBe("3 informations à compléter");
    expect(chaptersLabel(1)).toBe("dans 1 chapitre");
    expect(chaptersLabel(3)).toBe("dans 3 chapitres");
  });

  it("gives each drawer its icon, button and profile tab", () => {
    expect(KIND_META.staff).toEqual({
      icon: "👥",
      button: "Ajouter dans Moyens humains",
      profileSection: "moyens",
    });
    expect(KIND_META.equipment).toEqual({
      icon: "🧰",
      button: "Ajouter dans Moyens matériels",
      profileSection: "moyens",
    });
    expect(KIND_META.certification.button).toBe("Ajouter dans Certifications");
    expect(KIND_META.reference.button).toBe("Ajouter dans Références");
    expect(KIND_META.identity).toEqual({
      icon: "🆔",
      button: "Compléter mon profil",
      profileSection: "identite",
    });
    expect(KIND_META.tender).toEqual({
      icon: "✏️",
      button: null,
      profileSection: null,
    });
    expect(isCompanyKind("reference")).toBe(true);
    expect(isCompanyKind("tender")).toBe(false);
  });

  it("says where a completion stands", () => {
    const fill = (f: MissingItem["fill"]) => fillMessage(item({ fill: f }));
    expect(fill(null)).toBeNull();
    expect(fill({ status: "pending", outcome: null, error: null })).toBe(
      "Complétion en cours…",
    );
    expect(fill({ status: "running", outcome: null, error: null })).toBe(
      "Complétion en cours…",
    );
    expect(fill({ status: "done", outcome: "not_enough", error: null })).toBe(
      "La donnée ajoutée ne suffit pas pour cette phrase : précisez-la ou répondez directement.",
    );
    expect(fill({ status: "done", outcome: "filled", error: null })).toBeNull();
    expect(
      fill({
        status: "error",
        outcome: null,
        error: "Service d'IA indisponible : réessayez.",
      }),
    ).toBe("Service d'IA indisponible : réessayez.");
  });

  it("names the empty parts of the profile", () => {
    expect(
      gapMessages({ staff: false, equipment: true, references: false }),
    ).toEqual([
      {
        key: "equipment",
        text: "Votre profil n'a pas de matériel : le mémoire aura des trous.",
      },
    ]);
    expect(
      gapMessages({ staff: true, equipment: false, references: true }).map(
        (g) => g.text,
      ),
    ).toEqual([
      "Votre profil n'a pas de moyens humains : le mémoire aura des trous.",
      "Votre profil n'a pas de références : le mémoire aura des trous.",
    ]);
    expect(
      gapMessages({ staff: false, equipment: false, references: false }),
    ).toEqual([]);
  });
});

describe("the add-to-profile window", () => {
  it("names the missing item, or only says where the data goes", () => {
    expect(dialogIntro("nombre d'agents")).toBe(
      "Il manque : nombre d'agents. Ce que vous ajoutez est enregistré dans votre profil et servira à tous vos dossiers ; Pilao complète ensuite les phrases concernées.",
    );
    // before the drafting (« Avant la rédaction »): no marker, no sentence to complete
    expect(dialogIntro(null)).toBe(
      "Ce que vous ajoutez est enregistré dans votre profil et servira à tous vos dossiers.",
    );
  });
});

describe("where a missing item is answered", () => {
  // the items of the Louison Bobet DQE (ENG PRO, 23/11): they are about this tender
  const HERE = [
    "effectif affecté à chaque bâtiment et volume horaire hebdomadaire correspondant",
    "nom, qualification et coordonnées directes du chef d'équipe désigné pour ce marché.",
    "service de santé au travail auquel l'entreprise est rattachée et périodicité des visites appliquée aux agents du marché.",
    "matériel de vitrerie utilisé pour ce marché (raclettes, perches, produits)",
    "affectation des matériels à ce marché, avec quantités et modèles par bâtiment",
    "planning des interventions par site",
  ];

  it("answers in the dossier what is about this tender, even in a drawer of the profile", () => {
    for (const text of HERE)
      expect(answersHere(item({ text, kind: "staff" })), text).toBe(true);
  });

  it("sends to the profile what serves every dossier", () => {
    for (const text of [
      "nombre d'agents",
      "certification Qualipropre",
      "chiffre d'affaires des trois dernières années",
      "références de marchés similaires",
    ])
      expect(answersHere(item({ text, kind: "staff" })), text).toBe(false);
  });

  it("always answers in place a detail of the tender", () => {
    expect(
      answersHere(item({ text: "nom de l'acheteur", kind: "tender" })),
    ).toBe(true);
  });
});

describe("the example of an answer", () => {
  it("fits the question, and is only an example", () => {
    const ex = (text: string) => answerExample(text);
    expect(
      ex("effectif affecté à chaque bâtiment et volume horaire hebdomadaire"),
    ).toBe(
      "ex. Hôtel de ville : 2 agents, 15 h / semaine ; gymnase : 1 agent, 8 h / semaine",
    );
    expect(ex("coordonnées du chef d'équipe désigné pour ce marché")).toBe(
      "ex. M. Martin, chef d'équipe, 10 ans d'expérience, 06 12 34 56 78",
    );
    expect(ex("service de santé au travail et périodicité des visites")).toBe(
      "ex. AST Grand Lyon, visite tous les 2 ans",
    );
    expect(ex("matériel de vitrerie utilisé (raclettes, perches)")).toMatch(
      /^ex\. perches télescopiques/,
    );
    expect(ex("affectation des matériels par bâtiment")).toMatch(
      /^ex\. Bâtiment A : 1 autolaveuse/,
    );
    expect(ex("produits d'entretien utilisés")).toMatch(
      /^ex\. produits écolabellisés/,
    );
    expect(ex("planning des interventions")).toMatch(
      /^ex\. du lundi au vendredi/,
    );
    expect(ex("nombre d'agents")).toBe("ex. 4 agents, dont 1 chef d'équipe");
    expect(ex("quelque chose d'inattendu")).toBe(
      "Votre réponse, en quelques mots ou chiffres",
    );
    for (const text of ["nombre d'agents", "planning des interventions"])
      expect(ex(text).startsWith("ex. ")).toBe(true); // never mistaken for an answer
  });
});
