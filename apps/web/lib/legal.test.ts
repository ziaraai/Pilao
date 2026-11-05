import { describe, expect, it } from "vitest";

import { LEGAL, fact, missingFacts, versionDate } from "./legal";

describe("legal facts", () => {
  it("shows a missing fact as the product's [À COMPLÉTER] placeholder", () => {
    expect(fact(null, "hébergeur")).toBe("[À COMPLÉTER : hébergeur]");
    expect(fact("  ", "hébergeur")).toBe("[À COMPLÉTER : hébergeur]");
    expect(fact("Scaleway SAS", "hébergeur")).toBe("Scaleway SAS");
  });

  it("lists what is still to fill in before opening to clients", () => {
    const missing = missingFacts();
    expect(missing).toContain("publisher.name");
    expect(missing).toContain("host.name");
    const filled = structuredClone(LEGAL);
    filled.publisher.name = "Pilao SAS";
    filled.host = { name: "H", address: "A", phone: "P" };
    expect(missingFacts(filled)).not.toContain("publisher.name");
    expect(missingFacts(filled).some((m) => m.startsWith("host."))).toBe(false);
  });

  it("dates the version in French", () => {
    expect(versionDate("2026-11-05")).toBe("5 novembre 2026");
  });
});
