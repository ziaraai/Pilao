import { describe, expect, it } from "vitest";

import { chapterBody, highlight, inline, parseMarkdown } from "./markdown";

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

describe("passages to check", () => {
  it("marks numbers, names and commitments, never inside a longer word", () => {
    const parts = inline(
      "Jean Dupont encadre 45 agents (pas 145). Nous garantissons 2 h. **45**",
    );
    expect(
      highlight(parts, [
        { term: "45", kind: "number" },
        { term: "Jean Dupont", kind: "name" },
        { term: "Nous garantissons 2 h.", kind: "commitment" },
        { term: " ", kind: "name" },
      ]),
    ).toEqual([
      { t: "check", v: "Jean Dupont", kind: "name" },
      { t: "text", v: " encadre " },
      { t: "check", v: "45", kind: "number" },
      { t: "text", v: " agents (pas 145). " },
      { t: "check", v: "Nous garantissons 2 h.", kind: "commitment" },
      { t: "text", v: " " },
      { t: "strong", v: "45" },
    ]);
  });

  it("edits the body: the title stays the planned one", () => {
    expect(chapterBody("## 1. Moyens\n\nTexte\n\n## Sous-partie")).toBe(
      "Texte\n\n## Sous-partie",
    );
    expect(chapterBody("Texte sans titre")).toBe("Texte sans titre");
  });
});
