import { describe, expect, it } from "vitest";

import { hasModule, visibleNav } from "./modules";

const labels = (modules: string[]) => visibleNav(modules).map((n) => n.label);

describe("modules", () => {
  it("shows every entry with both modules, in the usual order", () => {
    expect(labels(["veille", "reponse"])).toEqual([
      "Tableau de bord",
      "Annonces",
      "Dossiers",
      "Coffre-fort",
      "Base documentaire",
      "Profil",
    ]);
  });

  it("keeps only the entries of the active modules", () => {
    expect(labels(["veille"])).toEqual([
      "Tableau de bord",
      "Annonces",
      "Profil",
    ]);
    expect(labels(["reponse"])).toEqual([
      "Tableau de bord",
      "Dossiers",
      "Coffre-fort",
      "Base documentaire",
      "Profil",
    ]);
  });

  it("always keeps the dashboard and the profile", () => {
    expect(labels([])).toEqual(["Tableau de bord", "Profil"]);
    expect(labels(["crm"])).toEqual(["Tableau de bord", "Profil"]);
  });

  it("tells whether a module is active", () => {
    expect(hasModule(["veille"], "veille")).toBe(true);
    expect(hasModule(["veille"], "reponse")).toBe(false);
    expect(hasModule([], "veille")).toBe(false);
  });
});
