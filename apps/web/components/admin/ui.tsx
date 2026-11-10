import Link from "next/link";
import type { ReactNode } from "react";

import type { Color } from "@/components/ui";

/** Counters of the administration: the colours of the application (ADR-038). */
const TILE: Record<Color, string> = {
  red: "border-red-300 border-l-red-500 bg-red-100 text-red-700",
  green:
    "border-emerald-300 border-l-emerald-500 bg-emerald-100 text-emerald-700",
  blue: "border-blue-300 border-l-blue-500 bg-blue-100 text-blue-700",
  amber: "border-amber-300 border-l-amber-500 bg-amber-100 text-amber-700",
  brand: "border-emerald-300 border-l-brand-green bg-[#dcfbf1] text-brand-navy",
  violet: "border-violet-300 border-l-violet-500 bg-violet-100 text-violet-700",
  sky: "border-sky-300 border-l-sky-500 bg-sky-100 text-sky-700",
  slate: "border-slate-300 border-l-slate-400 bg-white text-slate-600",
};

export function Tile({
  value,
  label,
  color,
  href,
}: {
  value: ReactNode;
  label: string;
  color: Color;
  href?: string;
}) {
  const box = `block rounded-lg border border-l-[6px] px-4 py-3 shadow-sm ${TILE[color]} ${href ? "hover:brightness-95" : ""}`;
  const content = (
    <>
      <span className="block text-2xl font-bold leading-tight">{value}</span>
      <span className="block text-xs font-semibold">{label}</span>
    </>
  );
  return href ? (
    <Link href={href} className={box}>
      {content}
    </Link>
  ) : (
    <div className={box}>{content}</div>
  );
}

/** Lot 1 of the administration only reads: said on every screen. */
export function ReadOnlyBadge() {
  return (
    <span className="inline-flex items-center gap-1.5 rounded-full bg-blue-100 px-2.5 py-0.5 align-middle text-xs font-semibold text-blue-800 ring-1 ring-inset ring-blue-300">
      <svg
        viewBox="0 0 24 24"
        className="h-3.5 w-3.5"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        aria-hidden="true"
      >
        <path d="M2 12s3.6-7 10-7 10 7 10 7-3.6 7-10 7-10-7-10-7Z" />
        <circle cx="12" cy="12" r="3" />
      </svg>
      Lecture seule
    </span>
  );
}

export function AdminTitle({
  title,
  subtitle,
  actions,
}: {
  title: string;
  subtitle?: ReactNode;
  actions?: ReactNode;
}) {
  return (
    <div className="mb-6 flex flex-wrap items-end justify-between gap-3">
      <div className="min-w-0">
        <h1 className="flex flex-wrap items-center gap-x-3 gap-y-1 text-2xl font-bold text-brand-navy">
          {title}
          <ReadOnlyBadge />
        </h1>
        {subtitle && <p className="mt-1 text-sm text-slate-600">{subtitle}</p>}
      </div>
      {actions}
    </div>
  );
}

/** A pill for a state: green fine, red wrong, amber to watch. */
export function Pill({
  tone,
  children,
}: {
  tone: "ok" | "danger" | "warning" | "neutral";
  children: ReactNode;
}) {
  const tones = {
    ok: "bg-emerald-100 text-emerald-800 ring-emerald-300",
    danger: "bg-red-100 text-red-800 ring-red-300",
    warning: "bg-amber-100 text-amber-900 ring-amber-300",
    neutral: "bg-slate-100 text-slate-700 ring-slate-300",
  };
  return (
    <span
      className={`inline-flex items-center whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${tones[tone]}`}
    >
      {children}
    </span>
  );
}
