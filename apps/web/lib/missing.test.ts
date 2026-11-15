import { describe, expect, it } from "vitest";

import {
  KIND_META,
  chaptersLabel,
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
