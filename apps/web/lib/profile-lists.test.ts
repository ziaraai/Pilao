import { describe, expect, it } from "vitest";

import {
  draftOf,
  payloadOf,
  referenceDraft,
  referencePayload,
} from "./profile-lists";
import type { Reference } from "./types";

const columns = [
  { key: "qualification" },
  { key: "count", type: "number" as const },
  { key: "description" },
];

describe("a line of the profile lists, edited in place", () => {
  it("fills the fields with what the line holds", () => {
    expect(
      draftOf(
        {
          id: "x",
          qualification: "NS ENVERENEMENT",
          count: 16,
          description: null,
        },
        columns,
      ),
    ).toEqual({
      qualification: "NS ENVERENEMENT",
      count: "16",
      description: "",
    });
  });

  it("sends what was typed: trimmed, numbers as numbers, empty as nothing", () => {
    expect(
      payloadOf(
        {
          qualification: "  Agent d'environnement ",
          count: "16",
          description: " ",
        },
        columns,
      ),
    ).toEqual({
      qualification: "Agent d'environnement",
      count: 16,
      description: null,
    });
  });
});

describe("a reference, edited in the form", () => {
  const ref: Reference = {
    id: "r",
    client_name: "Ville de Lyon",
    client_type: "public",
    title: "Nettoyage des écoles",
    location: "Lyon",
    department: "69",
    amount_cents: 12500050,
    year: 2024,
    duration_months: 36,
    description: "Trois groupes scolaires",
    cpv_codes: ["90911200"],
  };

  it("shows the amount as typed by a French user", () => {
    expect(referenceDraft(ref)).toEqual({
      client_name: "Ville de Lyon",
      client_type: "public",
      title: "Nettoyage des écoles",
      department: "69",
      amount: "125000,50",
      year: "2024",
    });
  });

  it("sends back the same values when nothing was changed", () => {
    expect(referencePayload(referenceDraft(ref))).toEqual({
      client_name: "Ville de Lyon",
      client_type: "public",
      title: "Nettoyage des écoles",
      department: "69",
      amount_cents: 12500050,
      year: 2024,
    });
  });
});
