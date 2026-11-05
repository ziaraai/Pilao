import { Fragment } from "react";

import {
  type Highlight,
  type Inline,
  type Marked,
  highlight,
  parseMarkdown,
} from "@/lib/markdown";

const CHECK_CLASS: Record<Highlight["kind"], string> = {
  number: "rounded bg-sky-100 px-0.5 text-sky-950 ring-1 ring-sky-300",
  name: "rounded bg-violet-100 px-0.5 text-violet-950 ring-1 ring-violet-300",
  commitment: "bg-orange-50 underline decoration-orange-400 decoration-2",
};
const CHECK_TITLE: Record<Highlight["kind"], string> = {
  number: "Chiffre absent de vos données : à vérifier",
  name: "Nom absent de vos données : à vérifier",
  commitment: "Engagement : à valider",
};

function Text({ parts, terms }: { parts: Inline[]; terms: Highlight[] }) {
  const marked: Marked[] = highlight(parts, terms);
  return (
    <>
      {marked.map((p, i) =>
        p.t === "strong" ? (
          <strong key={i}>{p.v}</strong>
        ) : p.t === "em" ? (
          <em key={i}>{p.v}</em>
        ) : p.t === "check" ? (
          <mark
            key={i}
            title={CHECK_TITLE[p.kind]}
            className={CHECK_CLASS[p.kind]}
          >
            {p.v}
          </mark>
        ) : p.t === "todo" ? (
          <mark
            key={i}
            className="rounded bg-amber-100 px-1 font-medium text-amber-900 ring-1 ring-amber-300"
          >
            [À COMPLÉTER : {p.v}]
          </mark>
        ) : (
          <Fragment key={i}>{p.v}</Fragment>
        ),
      )}
    </>
  );
}

/** A chapter as the buyer will read it. Titles start at h3: the page owns h1 and h2. */
export function Markdown({
  source,
  highlights = [],
}: {
  source: string;
  highlights?: Highlight[];
}) {
  return (
    <div className="space-y-3 text-sm leading-relaxed text-slate-800">
      {parseMarkdown(source).map((b, i) => {
        if (b.type === "heading") {
          const Tag = b.level <= 2 ? "h3" : b.level === 3 ? "h4" : "h5";
          const size =
            b.level <= 2
              ? "text-base font-semibold text-brand-navy"
              : "text-sm font-semibold text-slate-900";
          return (
            <Tag key={i} className={size}>
              <Text parts={b.text} terms={highlights} />
            </Tag>
          );
        }
        if (b.type === "list") {
          const Tag = b.ordered ? "ol" : "ul";
          return (
            <Tag
              key={i}
              className={`space-y-1 pl-5 ${b.ordered ? "list-decimal" : "list-disc"}`}
            >
              {b.items.map((item, j) => (
                <li key={j}>
                  <Text parts={item} terms={highlights} />
                </li>
              ))}
            </Tag>
          );
        }
        if (b.type === "table") {
          return (
            <div key={i} className="overflow-x-auto">
              <table className="min-w-full border-collapse text-left text-sm">
                <thead>
                  <tr>
                    {b.head.map((cell, j) => (
                      <th
                        key={j}
                        className="border border-slate-200 bg-slate-50 px-2 py-1 font-semibold"
                      >
                        <Text parts={cell} terms={highlights} />
                      </th>
                    ))}
                  </tr>
                </thead>
                <tbody>
                  {b.rows.map((row, j) => (
                    <tr key={j}>
                      {row.map((cell, k) => (
                        <td
                          key={k}
                          className="border border-slate-200 px-2 py-1"
                        >
                          <Text parts={cell} terms={highlights} />
                        </td>
                      ))}
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          );
        }
        return (
          <p key={i}>
            <Text parts={b.text} terms={highlights} />
          </p>
        );
      })}
    </div>
  );
}
