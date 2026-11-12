import { describe, expect, it } from "vitest";

import {
  bannerText,
  creditInput,
  creditLevel,
  missing,
  withPrice,
} from "./credits";

describe("credits", () => {
  it("tells when the credits run low or out", () => {
    expect(creditLevel(8, 100)).toBe("low");
    expect(creditLevel(20, 100)).toBe("ok");
    expect(creditLevel(0, 100)).toBe("empty");
    expect(creditLevel(1, 7)).toBe("low");
    expect(creditLevel(5, 0)).toBe("ok");
    expect(creditLevel(0, 0)).toBe("empty");
  });

  it("shows the price on a paid button", () => {
    expect(withPrice("Lancer l'analyse", 2)).toBe(
      "Lancer l'analyse · 2 crédits",
    );
    expect(withPrice("Régénérer", 1)).toBe("Régénérer · 1 crédit");
    expect(withPrice("Régénérer", 0)).toBe("Régénérer");
  });

  it("says what is missing, in credits only", () => {
    expect(missing(5, 3, null)).toBe(
      "Il faut 5 crédits, il vous en reste 3. Contactez Pilao.",
    );
    expect(missing(1, 0, "aide@pilao.test")).toBe(
      "Il faut 1 crédit, il vous en reste 0. Contactez Pilao : aide@pilao.test.",
    );
    expect(missing(2, 3, null)).toBeNull();
    expect(missing(0, 0, null)).toBeNull();
  });

  it("words the banner", () => {
    expect(bannerText("low", 8, null)).toBe("Il vous reste 8 crédits.");
    expect(bannerText("low", 1, null)).toBe("Il vous reste 1 crédit.");
    expect(bannerText("empty", 0, "aide@pilao.test")).toBe(
      "Vous n'avez plus de crédits : les actions payantes sont en pause. Contactez Pilao : aide@pilao.test.",
    );
    expect(bannerText("ok", 50, null)).toBeNull();
  });
});

describe("creditInput", () => {
  it("reads a whole number of credits within the limit", () => {
    expect(creditInput("0", 1000)).toBe(0);
    expect(creditInput(" 12 ", 1000)).toBe(12);
    expect(creditInput("1000", 1000)).toBe(1000);
  });
  it("refuses an empty, partial or out-of-range field instead of reading 0", () => {
    for (const raw of ["", "  ", "-1", "1.5", "1e3", "abc", "1001"])
      expect(creditInput(raw, 1000)).toBeNull();
  });
});
