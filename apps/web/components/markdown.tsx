import { Fragment } from "react";

import { type Inline, parseMarkdown } from "@/lib/markdown";

function Text({ parts }: { parts: Inline[] }) {
  return (
    <>
      {parts.map((p, i) =>
        p.t === "strong" ? (
          <strong key={i}>{p.v}</strong>
        ) : p.t === "em" ? (
          <em key={i}>{p.v}</em>
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
export function Markdown({ source }: { source: string }) {
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
              <Text parts={b.text} />
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
                  <Text parts={item} />
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
                        <Text parts={cell} />
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
                          <Text parts={cell} />
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
            <Text parts={b.text} />
          </p>
        );
      })}
    </div>
  );
}
