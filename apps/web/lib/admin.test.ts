import { describe, expect, it } from "vitest";

import type { AdminOrgUser } from "./types";

import {
  ADMIN_NAV,
  adminSignInPath,
  auditDetail,
  auditLabel,
  moduleShort,
  safeAdminNext,
  userActions,
} from "./admin";

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

  it("has eight screens, the overview first, the plans last", () => {
    expect(ADMIN_NAV.map((n) => n.href)).toEqual([
      "/admin",
      "/admin/entreprises",
      "/admin/couts-ia",
      "/admin/technique",
      "/admin/avis",
      "/admin/journal",
      "/admin/modules",
      "/admin/formules",
    ]);
    expect(ADMIN_NAV[6].label).toBe("Modules");
    expect(ADMIN_NAV[7].label).toBe("Formules");
  });

  it("names the journal's actions in French", () => {
    expect(auditLabel("organization_suspended")).toBe("Entreprise suspendue");
    expect(auditLabel("user_removed")).toBe("Utilisateur retiré");
    expect(auditLabel("login_failed")).toBe("Connexion refusée");
    expect(auditLabel("something_new")).toBe("something_new");
    expect(auditLabel("module_enabled")).toBe("Module activé");
    expect(auditLabel("module_disabled")).toBe("Module désactivé");
    expect(auditLabel("plan_created")).toBe("Formule créée");
    expect(auditLabel("plan_updated")).toBe("Formule modifiée");
    expect(auditLabel("plan_archived")).toBe("Formule archivée");
    expect(auditLabel("plan_unarchived")).toBe("Formule désarchivée");
    expect(auditLabel("plan_default_set")).toBe("Formule par défaut changée");
    expect(auditLabel("plan_changed")).toBe("Formule de l'entreprise changée");
    expect(auditLabel("credits_added")).toBe("Crédits ajoutés");
    expect(auditLabel("credit_price_changed")).toBe("Prix d'une action changé");
  });

  it("names the modules shortly in the companies list", () => {
    expect(moduleShort("veille")).toBe("Veille");
    expect(moduleShort("reponse")).toBe("Réponse");
    expect(moduleShort("crm")).toBe("crm");
  });

  it("sums up a journal line's details, never more", () => {
    expect(auditDetail({ email: "a@example.fr", role: "org_admin" })).toBe(
      "a@example.fr · rôle : Administrateur",
    );
    expect(auditDetail({ reason: "Impayé" })).toBe("Raison : Impayé");
    expect(auditDetail({ mode: "immediate", name: "Propreté" })).toBe(
      "Propreté · effacée tout de suite",
    );
    expect(auditDetail({ mode: "scheduled", name: "Propreté" })).toBe(
      "Propreté · effacement dans 30 jours",
    );
    expect(auditDetail({ left: 3 })).toBe("3 codes de secours restants");
    expect(auditDetail({ amount: 20, reason: "Geste" })).toBe(
      "20 crédits · Raison : Geste",
    );
    expect(auditDetail({ from: "Découverte", to: "Pilote" })).toBe(
      "Découverte → Pilote",
    );
    expect(
      auditDetail({
        action: "dce_analysis",
        name: "Analyse du DCE",
        from: 2,
        to: 3,
      }),
    ).toBe("Analyse du DCE · 2 → 3 crédits");
    expect(
      auditDetail({ module: "reponse", name: "Réponse aux appels d'offres" }),
    ).toBe("Réponse aux appels d'offres");
    expect(auditDetail({ by: "cli" })).toBe("—");
    expect(auditDetail({})).toBe("—");
  });
});

describe("actions on a company's user", () => {
  const user = (over: Partial<AdminOrgUser>): AdminOrgUser => ({
    id: "u",
    full_name: null,
    email: "a@example.fr",
    role: "org_member",
    email_verified: true,
    last_login_at: null,
    terms_version: null,
    status: "active",
    invited_at: null,
    has_sessions: false,
    ...over,
  });

  it("offers what makes sense for each state", () => {
    expect(userActions(user({ has_sessions: true }), false)).toEqual([
      "password-reset",
      "role",
      "logout",
      "remove",
    ]);
    expect(userActions(user({ status: "unverified" }), false)).toEqual([
      "verification",
      "password-reset",
      "role",
      "remove",
    ]);
    expect(userActions(user({ status: "invited" }), false)).toEqual([
      "invitation",
      "role",
      "remove",
    ]);
    expect(userActions(user({ status: "invitation_expired" }), false)).toEqual([
      "invitation",
      "role",
      "remove",
    ]);
  });

  it("sends nothing for a suspended company", () => {
    expect(userActions(user({ has_sessions: true }), true)).toEqual([
      "role",
      "logout",
      "remove",
    ]);
    expect(userActions(user({ status: "invited" }), true)).toEqual([
      "role",
      "remove",
    ]);
  });
});
