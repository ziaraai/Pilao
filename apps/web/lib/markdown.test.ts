import { describe, expect, it } from "vitest";

import { inline, parseMarkdown } from "./markdown";

describe("chapter markdown", () => {
  it("reads titles, paragraphs, lists and tables", () => {
    const blocks = parseMarkdown(
      [
        "## 2. Méthodologie",
        "",
        "Nous intervenons",
        "avant 8h.",
        "",
        "- quotidien",
        "* hebdomadaire",
        "1. Accueil",
        "2) Bureaux",
        "",
        "| Zone | Fréquence |",
        "|---|:---:|",
        "| Bureaux | **quotidienne** |",
        "Après le tableau.",
      ].join("\n"),
    );
    expect(blocks).toEqual([
      {
        type: "heading",
        level: 2,
        text: [{ t: "text", v: "2. Méthodologie" }],
      },
      {
        type: "paragraph",
        text: [{ t: "text", v: "Nous intervenons avant 8h." }],
      },
      {
        type: "list",
        ordered: false,
        items: [
          [{ t: "text", v: "quotidien" }],
          [{ t: "text", v: "hebdomadaire" }],
        ],
      },
      {
        type: "list",
        ordered: true,
        items: [[{ t: "text", v: "Accueil" }], [{ t: "text", v: "Bureaux" }]],
      },
      {
        type: "table",
        head: [[{ t: "text", v: "Zone" }], [{ t: "text", v: "Fréquence" }]],
        rows: [
          [[{ t: "text", v: "Bureaux" }], [{ t: "strong", v: "quotidienne" }]],
        ],
      },
      { type: "paragraph", text: [{ t: "text", v: "Après le tableau." }] },
    ]);
  });

  it("isolates the [À COMPLÉTER : …] markers so they can be highlighted", () => {
    expect(
      inline(
        "Nous affectons [À COMPLÉTER : nombre d'agents] agents, *formés*.",
      ),
    ).toEqual([
      { t: "text", v: "Nous affectons " },
      { t: "todo", v: "nombre d'agents" },
      { t: "text", v: " agents, " },
      { t: "em", v: "formés" },
      { t: "text", v: "." },
    ]);
    expect(inline("[à compléter: SIRET]")).toEqual([{ t: "todo", v: "SIRET" }]);
  });

  it("keeps HTML and odd characters as plain text", () => {
    expect(parseMarkdown("<script>alert(1)</script> 3 * 4 = 12_000_")).toEqual([
      {
        type: "paragraph",
        text: [{ t: "text", v: "<script>alert(1)</script> 3 * 4 = 12_000_" }],
      },
    ]);
  });
});
