import Link from "next/link";
import type { ReactNode } from "react";

import { versionDate } from "@/lib/legal";

export const LEGAL_PAGES = [
  { href: "/mentions-legales", label: "Mentions légales" },
  { href: "/confidentialite", label: "Confidentialité" },
  { href: "/conditions-utilisation", label: "Conditions d'utilisation" },
  { href: "/accord-de-traitement", label: "Accord de traitement des données" },
] as const;

/** Footer links, on every page (public pages and the application). */
export function LegalLinks({ className = "" }: { className?: string }) {
  return (
    <nav
      aria-label="Informations légales"
      className={`flex flex-wrap justify-center gap-x-4 gap-y-1 text-xs text-slate-500 ${className}`}
    >
      {LEGAL_PAGES.map((p) => (
        <Link key={p.href} href={p.href} className="hover:underline">
          {p.label}
        </Link>
      ))}
    </nav>
  );
}

export function LegalPage({
  title,
  intro,
  children,
}: {
  title: string;
  intro?: ReactNode;
  children: ReactNode;
}) {
  return (
    <article className="space-y-6 text-sm leading-6 text-slate-700">
      <header className="space-y-2">
        <h1 className="text-2xl font-bold text-brand-navy">{title}</h1>
        <p className="text-xs text-slate-500">Version du {versionDate()}</p>
        {intro && <p>{intro}</p>}
      </header>
      {children}
    </article>
  );
}

export function Section({
  title,
  id,
  children,
}: {
  title: string;
  id?: string;
  children: ReactNode;
}) {
  return (
    <section id={id} className="space-y-2">
      <h2 className="text-base font-semibold text-brand-navy">{title}</h2>
      {children}
    </section>
  );
}

export function List({ children }: { children: ReactNode }) {
  return <ul className="list-disc space-y-1 pl-5">{children}</ul>;
}

/** A fact still to decide: highlighted like the « [À COMPLÉTER] » of the memoirs. */
export function Fact({ children }: { children: string }) {
  return children.startsWith("[À COMPLÉTER") ? (
    <mark className="rounded bg-amber-100 px-1 text-amber-900">{children}</mark>
  ) : (
    <>{children}</>
  );
}
