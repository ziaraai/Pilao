import { describe, expect, it } from "vitest";

import { applyTool, TOOLS } from "./editor";

const tool = (label: string) => TOOLS.find((t) => t.label === label)!;
const selected = (r: { text: string; from: number; to: number }) =>
  r.text.slice(r.from, r.to);

describe("chapter editor toolbar", () => {
  it("wraps the selection and keeps it selected", () => {
    const r = applyTool(tool("G"), "Nous intervenons vite.", 17, 21);
    expect(r.text).toBe("Nous intervenons **vite**.");
    expect(selected(r)).toBe("vite");
  });

  it("selects the placeholder of a marker, ready to be typed over", () => {
    const r = applyTool(tool("[À COMPLÉTER]"), "Équipe : ", 9, 9);
    expect(r.text).toBe("Équipe : [À COMPLÉTER : information manquante]");
    expect(selected(r)).toBe("information manquante");
    expect(selected(applyTool(tool("Sous-titre"), "", 0, 0))).toBe(
      "Sous-titre",
    );
  });

  it("turns each selected line into a list item", () => {
    expect(applyTool(tool("1. Liste"), "Accueil\nBureaux", 0, 15).text).toBe(
      "1. Accueil\n2. Bureaux",
    );
  });
});
