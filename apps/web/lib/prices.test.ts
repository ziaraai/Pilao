import { describe, expect, it } from "vitest";

import {
  bySection,
  decimalText,
  hoursInput,
  lineHint,
  missingText,
  quantityText,
  ratesSummary,
  sourceText,
} from "@/lib/prices";
import type { PriceLine, Rates } from "@/lib/types";

const RATES: Rates = {
  hourly_rate_cents: 2500,
  night_pct: 25,
  sunday_pct: null,
  holiday_pct: 100,
};

function line(over: Partial<PriceLine> = {}): PriceLine {
  return {
    id: "DQE!B5",
    section: "prestation quotidienne",
    label: "Gymnase A",
    unit: "jour",
    quantity: "208",
    hourly: false,
    surcharge: "none",
    hours: null,
    price_cents: null,
    total_cents: null,
    source: "none",
    ...over,
  };
}

describe("prices", () => {
  it("reads hours the French way", () => {
    expect(hoursInput("2,5")).toBe("2.5");
    expect(hoursInput(" 3 ")).toBe("3");
    expect(hoursInput("")).toBeNull();
    expect(hoursInput("abc")).toBe("invalid");
    expect(hoursInput("0")).toBe("invalid");
    expect(decimalText("2.5")).toBe("2,5");
  });

  it("sums up the rates", () => {
    expect(ratesSummary(RATES)).toBe(
      "25,00 € HT/h · nuit +25 % · dimanche — · jour férié +100 %",
    );
    expect(
      ratesSummary({ ...RATES, hourly_rate_cents: null }).startsWith(
        "taux horaire à saisir",
      ),
    ).toBe(true);
  });

  it("says what a line still needs, never a guess", () => {
    expect(lineHint(line({ price_cents: 6250 }), RATES, null)).toBeNull();
    expect(lineHint(line(), RATES, null)).toBe("Heures ou prix à saisir.");
    const noRate = { ...RATES, hourly_rate_cents: null };
    expect(lineHint(line({ hours: "2" }), noRate, null)).toBe(
      "Saisissez votre taux horaire.",
    );
    expect(
      lineHint(line({ hourly: true, surcharge: "sunday" }), RATES, null),
    ).toBe("Saisissez votre majoration « dimanche » ou un prix.");
  });

  it("explains each price", () => {
    expect(sourceText(line({ source: "hours", hours: "2.5" }), 2500)).toBe(
      "2,5 h × 25,00 €",
    );
    expect(
      sourceText(line({ source: "hourly", surcharge: "night" }), 2500),
    ).toBe("taux + majoration nuit");
    expect(sourceText(line({ source: "price" }), null)).toBe("prix saisi");
  });

  it("groups the lines by section in order", () => {
    const groups = bySection([
      line({ id: "a" }),
      line({ id: "b" }),
      line({ id: "c", section: "prestation annuelle" }),
    ]);
    expect(groups.map((g) => [g.section, g.lines.length])).toEqual([
      ["prestation quotidienne", 2],
      ["prestation annuelle", 1],
    ]);
    expect(missingText(0)).toBe("Tous les prix sont remplis");
    expect(missingText(3)).toBe("3 prix à compléter");
  });

  it("writes the quantities with their unit", () => {
    expect(quantityText("208", "jour")).toBe("208 jours");
    expect(quantityText("2", "heure")).toBe("2 heures");
    expect(quantityText("1", "forfait")).toBe("1 forfait");
    expect(quantityText("12.5", "m²")).toBe("12,5 m²");
    expect(quantityText("3", "u")).toBe("3 u");
    expect(quantityText(null, "jour")).toBe("—");
  });
});
