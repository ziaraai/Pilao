/**
 * The small Markdown subset the chapters use (titles, paragraphs, lists, tables, bold,
 * italics), parsed into data and rendered as React elements: no HTML string is ever
 * injected, whatever the model wrote. `[À COMPLÉTER : …]` markers become their own token so
 * the page can highlight them (US-4.2 CA3).
 */

export type Inline =
  | { t: "text"; v: string }
  | { t: "strong"; v: string }
  | { t: "em"; v: string }
  | { t: "todo"; v: string };

export type Block =
  | { type: "heading"; level: number; text: Inline[] }
  | { type: "paragraph"; text: Inline[] }
  | { type: "list"; ordered: boolean; items: Inline[][] }
  | { type: "table"; head: Inline[][]; rows: Inline[][][] };

const TODO = /\[\s*À\s+COMPLÉTER\s*:\s*([^\]]+)\]/giu;
// "_" only around words, as in CommonMark: 12_000_ or file_name stay as they are.
const EMPHASIS =
  /\*\*(.+?)\*\*|(?<![\p{L}\d_])__(.+?)__(?![\p{L}\d_])|\*(?!\s)(.+?)\*|(?<![\p{L}\d_])_(?!\s)(.+?)_(?![\p{L}\d_])/gu;
const HEADING = /^(#{1,6})\s+(.*)$/;
const BULLET = /^\s*[-*•]\s+(.*)$/;
const NUMBERED = /^\s*\d+[.)]\s+(.*)$/;
const TABLE_RULE = /^\s*\|?\s*:?-{3,}:?\s*(\|\s*:?-{3,}:?\s*)*\|?\s*$/;

function emphasis(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of text.matchAll(EMPHASIS)) {
    if (m.index > last) out.push({ t: "text", v: text.slice(last, m.index) });
    if (m[1] ?? m[2]) out.push({ t: "strong", v: (m[1] ?? m[2]) as string });
    else out.push({ t: "em", v: (m[3] ?? m[4]) as string });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push({ t: "text", v: text.slice(last) });
  return out;
}

export function inline(text: string): Inline[] {
  const out: Inline[] = [];
  let last = 0;
  for (const m of text.matchAll(TODO)) {
    if (m.index > last) out.push(...emphasis(text.slice(last, m.index)));
    out.push({ t: "todo", v: m[1].trim() });
    last = m.index + m[0].length;
  }
  if (last < text.length) out.push(...emphasis(text.slice(last)));
  return out;
}

function cells(line: string): string[] {
  return line
    .trim()
    .replace(/^\|/, "")
    .replace(/\|$/, "")
    .split("|")
    .map((c) => c.trim());
}

export function parseMarkdown(markdown: string): Block[] {
  const lines = markdown.replace(/\r\n?/g, "\n").split("\n");
  const blocks: Block[] = [];
  let paragraph: string[] = [];
  const flush = () => {
    if (paragraph.length)
      blocks.push({ type: "paragraph", text: inline(paragraph.join(" ")) });
    paragraph = [];
  };

  for (let i = 0; i < lines.length; i++) {
    const line = lines[i];
    const heading = HEADING.exec(line);
    if (!line.trim()) {
      flush();
    } else if (heading) {
      flush();
      blocks.push({
        type: "heading",
        level: heading[1].length,
        text: inline(heading[2].trim()),
      });
    } else if (
      line.trim().startsWith("|") &&
      TABLE_RULE.test(lines[i + 1] ?? "")
    ) {
      flush();
      const head = cells(line).map(inline);
      const rows: Inline[][][] = [];
      i += 2;
      while (i < lines.length && lines[i].trim().startsWith("|")) {
        rows.push(cells(lines[i]).map(inline));
        i++;
      }
      i--;
      blocks.push({ type: "table", head, rows });
    } else if (BULLET.test(line) || NUMBERED.test(line)) {
      flush();
      const ordered = !BULLET.test(line);
      const pattern = ordered ? NUMBERED : BULLET;
      const items: Inline[][] = [];
      while (i < lines.length && pattern.test(lines[i])) {
        items.push(inline((pattern.exec(lines[i]) as RegExpExecArray)[1]));
        i++;
      }
      i--;
      blocks.push({ type: "list", ordered, items });
    } else {
      paragraph.push(line.trim());
    }
  }
  flush();
  return blocks;
}
