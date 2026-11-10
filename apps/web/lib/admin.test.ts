import { describe, expect, it } from "vitest";

import { ADMIN_NAV, adminSignInPath, safeAdminNext } from "./admin";

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

  it("sends an expired session to the sign-in page, then back to the same screen", () => {
    expect(adminSignInPath("/admin/couts-ia", "?mois=2026-10")).toBe(
      "/admin/connexion?suite=%2Fadmin%2Fcouts-ia%3Fmois%3D2026-10",
    );
    expect(adminSignInPath("/admin", "")).toBe(
      "/admin/connexion?suite=%2Fadmin",
    );
    expect(
      safeAdminNext(
        decodeURIComponent(
          adminSignInPath("/admin/technique", "").split("=")[1],
        ),
      ),
    ).toBe("/admin/technique");
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
