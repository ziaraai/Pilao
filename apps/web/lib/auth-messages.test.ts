import { describe, expect, it } from "vitest";

import { signInNotice } from "./auth-messages";

describe("signInNotice", () => {
  it("says why a page sent the user back to sign in", () => {
    expect(signInNotice(new URLSearchParams("suspendu=1"))).toEqual({
      tone: "danger",
      text: "L'accès de votre entreprise à Pilao est suspendu.",
    });
  });

  it("confirms a new password", () => {
    expect(signInNotice(new URLSearchParams("mot-de-passe=change"))).toEqual({
      tone: "ok",
      text: "Mot de passe enregistré.",
    });
  });

  it("says nothing otherwise", () => {
    expect(signInNotice(new URLSearchParams(""))).toBeNull();
    expect(signInNotice(new URLSearchParams("suite=/profil"))).toBeNull();
  });
});
