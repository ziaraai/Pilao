import { describe, expect, it } from "vitest";

import { controlClass } from "@/components/ui";

import { validationMessage } from "./api";
import {
  centsToInput,
  formatCents,
  formatDate,
  formatDateTimeShort,
  formatDuration,
  minutesToHours,
  parseHours,
  fromParisInput,
  parseEuros,
  splitList,
  toParisInput,
} from "./format";

describe("money", () => {
  it("parses what French users type into cents", () => {
    expect(parseEuros("12 500,50")).toBe(1250050);
    expect(parseEuros("12500.5 €")).toBe(1250050);
    expect(parseEuros("800")).toBe(80000);
    expect(parseEuros("")).toBeNull();
    expect(parseEuros("douze")).toBeNull();
    expect(parseEuros("1,234")).toBeNull(); // 3 decimals: ambiguous, refused
  });
  it("formats cents back", () => {
    expect(formatCents(1250050)).toBe("12 500,50 €");
    expect(formatCents(null)).toBe("—");
    expect(centsToInput(1250000)).toBe("12500");
    expect(centsToInput(1250050)).toBe("12500,50");
  });
});

describe("dates in Paris time", () => {
  it("keeps calendar days as they are", () => {
    expect(formatDate("2027-04-15")).toBe("15 avril 2027");
  });
  it("writes a short date and time, as the public platforms do", () => {
    expect(formatDateTimeShort("2026-11-24T11:00:00Z")).toBe(
      "24/11/2026 12:00",
    );
    expect(formatDateTimeShort("2027-07-01T07:30:00Z")).toBe(
      "01/07/2027 09:30",
    );
    expect(formatDateTimeShort(null)).toBe("—");
  });
  it("round-trips datetime-local values in winter and summer", () => {
    for (const local of ["2026-12-15T12:00", "2027-07-01T09:30"]) {
      const iso = fromParisInput(local);
      expect(iso).not.toBeNull();
      expect(toParisInput(iso)).toBe(local);
    }
    expect(fromParisInput("2026-12-15T12:00")).toBe("2026-12-15T11:00:00.000Z");
    expect(fromParisInput("2027-07-01T09:30")).toBe("2027-07-01T07:30:00.000Z");
  });
});

describe("lists and errors", () => {
  it("splits keyword lists", () => {
    expect(splitList("nettoyage, vitrerie;\nnettoyage , ")).toEqual([
      "nettoyage",
      "vitrerie",
    ]);
  });
  it("turns validation errors into French", () => {
    expect(
      validationMessage([
        {
          loc: ["body", "password"],
          msg: "String should have at least 12 characters",
        },
      ]),
    ).toBe("Mot de passe : 12 caractères minimum.");
    expect(
      validationMessage([
        { loc: ["body", "siret"], msg: "Value error, SIRET invalide" },
      ]),
    ).toBe("SIRET invalide");
    expect(
      validationMessage([
        { loc: ["body", "email"], msg: "value is not a valid email address" },
      ]),
    ).toBe("Adresse e-mail invalide.");
  });
});

describe("control widths", () => {
  it("is full width by default and yields to an explicit width", () => {
    expect(controlClass()).toContain("w-full");
    expect(controlClass("w-24")).not.toContain("w-full");
    expect(controlClass("min-w-64 flex-1")).not.toContain("w-full");
    expect(controlClass("text-xs")).toContain("w-full");
  });
});

describe("durations", () => {
  it("reads hours the way people write them", () => {
    expect(parseHours("2")).toBe(120);
    expect(parseHours("2,5")).toBe(150);
    expect(parseHours("2.5")).toBe(150);
    expect(parseHours("2h30")).toBe(150);
    expect(parseHours("2 h 30")).toBe(150);
    expect(parseHours("8h")).toBe(480);
    expect(parseHours("")).toBeNull();
    expect(parseHours("2h75")).toBeNull();
    expect(parseHours("deux heures")).toBeNull();
  });

  it("shows minutes as hours", () => {
    expect(minutesToHours(150)).toBe("2,5");
    expect(minutesToHours(null)).toBe("");
    expect(formatDuration(45)).toBe("45 min");
    expect(formatDuration(360)).toBe("6 h");
    expect(formatDuration(390)).toBe("6 h 30");
  });
});
