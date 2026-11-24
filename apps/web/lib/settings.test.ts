import { describe, expect, it } from "vitest";

import {
  dollars,
  eur,
  mailboxSummary,
  matches,
  originLabel,
  robotSummary,
} from "./settings";

describe("settings", () => {
  it("writes prices in euros per million tokens, and dollars", () => {
    expect(eur(0.086)).toBe("0,086 €");
    expect(eur(0.43)).toBe("0,43 €");
    expect(eur(12)).toBe("12 €");
    expect(eur(null)).toBe("—");
    expect(dollars(3.68)).toBe("3,68 $");
    expect(dollars(5)).toBe("5,00 $");
  });
  it("finds a model by its name or identifier, without case or accents", () => {
    const m = {
      id: "anthropic/claude-haiku-5.5",
      name: "Anthropic: Claude Haiku 5.5",
    };
    expect(matches(m, "HAÏKU")).toBe(true);
    expect(matches(m, "anthropic/claude")).toBe(true);
    expect(matches(m, "  ")).toBe(true);
    expect(matches(m, "mistral")).toBe(false);
  });
  it("says where a value comes from", () => {
    expect(originLabel("admin")).toBe("réglé ici");
    expect(originLabel("server")).toBe("valeur du serveur");
    expect(originLabel("none")).toBe("aucune");
  });

  it("sums up the DCE robot", () => {
    const robot = {
      enabled: true,
      origin: "server" as const,
      server_value: true,
      succeeded_24h: 12,
      failed_24h: 1,
    };
    expect(robotSummary(robot)).toBe(
      "Activé — 12 réussies, 1 en échec sur 24 h",
    );
    expect(robotSummary({ ...robot, enabled: false })).toBe(
      "Coupé — mode guidé pour tous les clients",
    );
  });
  it("sums up the DCE mailbox in one line (ADR-055)", () => {
    const box = {
      enabled: true,
      origin: "admin" as const,
      address: "dce@pilao.pro",
      password_source: "admin" as const,
      received_24h: 3,
      to_sort: 1,
    };
    expect(mailboxSummary(box)).toBe(
      "Active — 3 e-mails reçus sur 24 h, 1 à classer chez les clients",
    );
    expect(mailboxSummary({ ...box, received_24h: 1, to_sort: 0 })).toBe(
      "Active — 1 e-mail reçu sur 24 h",
    );
    expect(mailboxSummary({ ...box, enabled: false })).toBe(
      "Coupée — l'adresse n'est pas montrée aux clients",
    );
    expect(
      mailboxSummary({ ...box, enabled: false, password_source: "none" }),
    ).toBe("Coupée — mot de passe de la boîte à enregistrer");
  });
});
