import { describe, expect, it } from "vitest";

import {
  CERTIFICATION_COLUMNS,
  EQUIPMENT_COLUMNS,
  HUMAN_RESOURCE_COLUMNS,
} from "@/lib/profile-columns";

describe("the fields of the profile's lists", () => {
  it("each show an example in grey, except the dates", () => {
    for (const c of [
      ...HUMAN_RESOURCE_COLUMNS,
      ...EQUIPMENT_COLUMNS,
      ...CERTIFICATION_COLUMNS,
    ].filter((c) => c.type !== "date"))
      expect(c.placeholder, c.label).toMatch(/^ex\. /);
  });

  it("say what « Précisions » means", () => {
    const precisions = HUMAN_RESOURCE_COLUMNS.find(
      (c) => c.key === "description",
    );
    expect(precisions?.placeholder).toBe("ex. CQP, temps partiel");
    expect(precisions?.hint).toBe(
      "diplômes, habilitations, temps de travail, ancienneté : Pilao les reprend dans le mémoire.",
    );
  });
});
