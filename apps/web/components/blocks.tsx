"use client";

/**
 * Building blocks that keep a page readable (spec « Page du dossier en onglets », § 5.8):
 * tabs, a block that unfolds (title + one-line summary + badges), a summary tile, a level
 * badge and a light table. Made for the dossier page, meant for the other pages next.
 */
import { useRef, type KeyboardEvent, type ReactNode } from "react";

import { Badge, tableHead } from "@/components/ui";
import type { Tone } from "@/lib/labels";

// ---------- tabs -------------------------------------------------------------------------

export function Tabs({
  tabs,
  active,
  done,
  alert,
  onSelect,
  label = "Étapes du dossier",
}: {
  tabs: { id: string; label: string }[];
  active: string;
  done: Record<string, boolean>;
  alert?: Record<string, boolean>;
  onSelect: (id: string) => void;
  label?: string;
}) {
  const refs = useRef<Record<string, HTMLButtonElement | null>>({});

  function onKey(e: KeyboardEvent<HTMLDivElement>) {
    if (e.key !== "ArrowRight" && e.key !== "ArrowLeft") return;
    e.preventDefault();
    const i = tabs.findIndex((t) => t.id === active);
    const step = e.key === "ArrowRight" ? 1 : -1;
    const next = tabs[(i + step + tabs.length) % tabs.length];
    onSelect(next.id);
    refs.current[next.id]?.focus();
  }

  return (
    <div
      role="tablist"
      aria-label={label}
      onKeyDown={onKey}
      className="-mx-4 flex gap-1 overflow-x-auto border-b-2 border-slate-200 px-4 sm:mx-0 sm:px-0"
    >
      {tabs.map((t) => {
        const selected = t.id === active;
        return (
          <button
            key={t.id}
            ref={(el) => {
              refs.current[t.id] = el;
            }}
            type="button"
            role="tab"
            id={`tab-${t.id}`}
            aria-selected={selected}
            aria-controls={`panel-${t.id}`}
            tabIndex={selected ? 0 : -1}
            onClick={() => onSelect(t.id)}
            className={`-mb-0.5 inline-flex min-h-11 shrink-0 items-center gap-1.5 border-b-[3px] px-4 text-sm font-semibold whitespace-nowrap focus-visible:outline-2 focus-visible:outline-brand-navy ${
              selected
                ? "border-brand-navy text-brand-navy"
                : "border-transparent text-slate-600 hover:text-brand-navy"
            }`}
          >
            {done[t.id] && (
              <svg
                viewBox="0 0 24 24"
                className="h-4 w-4 text-emerald-700"
                fill="none"
                stroke="currentColor"
                strokeWidth="2.5"
                strokeLinecap="round"
                strokeLinejoin="round"
                aria-hidden="true"
              >
                <path d="M5 12l5 5L20 7" />
              </svg>
            )}
            {t.label}
            {done[t.id] && <span className="sr-only"> (fait)</span>}
            {alert?.[t.id] && (
              <span
                className="h-2.5 w-2.5 rounded-full bg-red-600"
                aria-label="point bloquant"
                role="img"
              />
            )}
          </button>
        );
      })}
    </div>
  );
}

export function TabPanel({
  id,
  active,
  children,
}: {
  id: string;
  active: boolean;
  children: ReactNode;
}) {
  return (
    <div
      role="tabpanel"
      id={`panel-${id}`}
      aria-labelledby={`tab-${id}`}
      hidden={!active}
      className="space-y-6"
    >
      {children}
    </div>
  );
}

// ---------- disclosure -------------------------------------------------------------------

export type SummaryBadge = { label: string; tone: string };

const BADGE_TONE: Record<string, Tone> = {
  blocking: "danger",
  danger: "danger",
  warning: "warning",
  info: "info",
  ok: "ok",
  neutral: "neutral",
};

export function Disclosure({
  id,
  title,
  summary,
  badges = [],
  open,
  onToggle,
  children,
}: {
  id: string;
  title: string;
  summary?: ReactNode;
  badges?: SummaryBadge[];
  open: boolean;
  onToggle: () => void;
  children: ReactNode;
}) {
  return (
    <section
      id={id}
      className="scroll-mt-20 overflow-hidden rounded-lg border border-slate-300 bg-white shadow-sm"
    >
      <h2 className="m-0">
        <button
          type="button"
          aria-expanded={open}
          aria-controls={`${id}-contenu`}
          onClick={onToggle}
          className="flex min-h-14 w-full items-center gap-3 px-5 py-3 text-left hover:bg-slate-50 focus-visible:outline-2 focus-visible:outline-brand-navy"
        >
          <span className="flex min-w-0 flex-1 flex-col gap-1">
            <span className="text-base font-bold text-brand-navy">{title}</span>
            {summary && (
              <span className="text-sm font-normal text-slate-600">
                {summary}
              </span>
            )}
          </span>
          {badges.length > 0 && (
            <span className="hidden flex-wrap justify-end gap-1.5 sm:flex">
              {badges.map((b) => (
                <Badge key={b.label} tone={BADGE_TONE[b.tone] ?? "neutral"}>
                  {b.label}
                </Badge>
              ))}
            </span>
          )}
          <svg
            viewBox="0 0 24 24"
            className={`h-5 w-5 shrink-0 text-slate-500 transition-transform ${open ? "rotate-90" : ""}`}
            fill="none"
            stroke="currentColor"
            strokeWidth="2"
            strokeLinecap="round"
            strokeLinejoin="round"
            aria-hidden="true"
          >
            <path d="M9 6l6 6-6 6" />
          </svg>
        </button>
      </h2>
      {badges.length > 0 && !open && (
        <div className="flex flex-wrap gap-1.5 px-5 pb-3 sm:hidden">
          {badges.map((b) => (
            <Badge key={b.label} tone={BADGE_TONE[b.tone] ?? "neutral"}>
              {b.label}
            </Badge>
          ))}
        </div>
      )}
      {open && (
        <div
          id={`${id}-contenu`}
          className="border-t border-slate-200 px-5 py-4"
        >
          {children}
        </div>
      )}
    </section>
  );
}

// ---------- tile, level badge, table -----------------------------------------------------

const TILE_VALUE: Record<string, string> = {
  neutral: "text-brand-navy",
  ok: "text-emerald-800",
  warning: "text-amber-800",
  danger: "text-red-700",
};

export function StatTile({
  label,
  value,
  sub,
  tone = "neutral",
}: {
  label: string;
  value: string;
  sub?: string;
  tone?: "neutral" | "ok" | "warning" | "danger";
}) {
  return (
    <div className="flex flex-col gap-1 rounded-lg border border-slate-300 bg-white p-4 shadow-sm">
      <span className="text-xs font-semibold text-slate-600">{label}</span>
      <span className={`text-lg leading-snug font-bold ${TILE_VALUE[tone]}`}>
        {value}
      </span>
      {sub && <span className="text-sm text-slate-600">{sub}</span>}
    </div>
  );
}

const LEVEL: Record<
  "blocking" | "warning" | "info",
  { label: string; tone: Tone }
> = {
  blocking: { label: "Bloquant", tone: "danger" },
  warning: { label: "Attention", tone: "warning" },
  info: { label: "À noter", tone: "info" },
};

export function LevelBadge({
  level,
}: {
  level: "blocking" | "warning" | "info";
}) {
  return <Badge tone={LEVEL[level].tone}>{LEVEL[level].label}</Badge>;
}

export function DataTable({
  head,
  children,
  minWidth = 560,
}: {
  head: string[];
  children: ReactNode;
  minWidth?: number;
}) {
  return (
    <div className="overflow-x-auto">
      <table
        className="w-full text-left text-sm"
        style={{ minWidth: `${minWidth}px` }}
      >
        <thead className={tableHead}>
          <tr>
            {head.map((h) => (
              <th key={h} scope="col" className="px-3 py-2">
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>{children}</tbody>
      </table>
    </div>
  );
}
