import { describe, expect, it } from "vitest";

import { ADMIN_NAV, safeAdminNext } from "./admin";

describe("administration", () => {
  it("goes back, after sign-in, only to a page of the administration", () => {
    expect(safeAdminNext("/admin/entreprises")).toBe("/admin/entreprises");
    expect(safeAdminNext("/admin")).toBe("/admin");
    expect(safeAdminNext("/admin/couts-ia?mois=2026-11")).toBe(
      "/admin/couts-ia?mois=2026-11",
    );
    for (const bad of [
      null,
      "",
      "/tableau-de-bord",
      "//evil.example/admin",
      "https://evil.example",
      "/administrateur",
      "/admin/connexion",
      "/admin/activation?jeton=x",
    ])
      expect(safeAdminNext(bad)).toBe("/admin");
  });

  it("has five screens, the overview first", () => {
    expect(ADMIN_NAV.map((n) => n.href)).toEqual([
      "/admin",
      "/admin/entreprises",
      "/admin/couts-ia",
      "/admin/technique",
      "/admin/avis",
    ]);
  });
});
