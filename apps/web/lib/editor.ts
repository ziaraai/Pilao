/** The chapter editor's toolbar (US-4.4 CA1): Markdown inserted around the selection. */

export type Tool = {
  label: string;
  title: string;
  apply: (selected: string) => { text: string; select?: [number, number] };
};

const lines = (s: string, prefix: (i: number) => string) =>
  s
    .split("\n")
    .map((l, i) => prefix(i) + l)
    .join("\n");

const TODO_OPEN = "[À COMPLÉTER : ";

export const TOOLS: Tool[] = [
  {
    label: "G",
    title: "Gras (Ctrl+B)",
    apply: (s) => ({ text: `**${s || "texte"}**`, select: [2, 2] }),
  },
  {
    label: "I",
    title: "Italique (Ctrl+I)",
    apply: (s) => ({ text: `*${s || "texte"}*`, select: [1, 1] }),
  },
  {
    label: "Sous-titre",
    title: "Sous-titre",
    apply: (s) => ({ text: `\n### ${s || "Sous-titre"}\n`, select: [5, 1] }),
  },
  {
    label: "• Liste",
    title: "Liste à puces",
    apply: (s) => ({ text: lines(s || "élément", () => "- ") }),
  },
  {
    label: "1. Liste",
    title: "Liste numérotée",
    apply: (s) => ({ text: lines(s || "étape", (i) => `${i + 1}. `) }),
  },
  {
    label: "Tableau",
    title: "Tableau",
    apply: () => ({
      text: "\n| Colonne 1 | Colonne 2 |\n|---|---|\n| … | … |\n",
    }),
  },
  {
    label: "[À COMPLÉTER]",
    title: "Signaler une information à compléter",
    apply: (s) => ({
      text: `${TODO_OPEN}${s || "information manquante"}]`,
      select: [TODO_OPEN.length, 1], // the description is selected, ready to be typed
    }),
  },
];

/** The new text, and what to select in it (the placeholder, ready to be typed over). */
export function applyTool(
  tool: Tool,
  text: string,
  start: number,
  end: number,
): { text: string; from: number; to: number } {
  const out = tool.apply(text.slice(start, end));
  const [from, to] = out.select
    ? [start + out.select[0], start + out.text.length - out.select[1]]
    : [start + out.text.length, start + out.text.length];
  return { text: text.slice(0, start) + out.text + text.slice(end), from, to };
}
