"use client";

import Link from "next/link";
import { useState } from "react";

import { Alert, Badge, Card, Loading } from "@/components/ui";
import { useMe } from "@/lib/auth";
import { formatCents, formatDateTime, formatDuration } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type {
  BidProgress,
  BidStage,
  Dashboard,
  DashboardAction,
  DashboardStep,
} from "@/lib/types";

const SHOWN = 6; // actions shown before « Voir tout »
const STAGES: { key: BidStage; label: string }[] = [
  { key: "dce", label: "DCE" },
  { key: "analysis", label: "Analyse" },
  { key: "memoir", label: "Mémoire" },
  { key: "submitted", label: "Déposé" },
];
const LEVEL = {
  urgent: { dot: "bg-red-500", label: "Urgent" },
  soon: { dot: "bg-amber-400", label: "Bientôt" },
  todo: { dot: "bg-slate-300", label: "À faire" },
} as const;

const today = new Intl.DateTimeFormat("fr-FR", {
  weekday: "long",
  day: "numeric",
  month: "long",
  timeZone: "Europe/Paris",
});

/** US-5.3: what to do now, then the new notices, the bids in progress, the results. */
export default function DashboardPage() {
  const { me } = useMe();
  const board = useApi<Dashboard>("/dashboard");
  if (board.error && !board.data)
    return <Alert tone="danger">{board.error}</Alert>;
  if (!board.data) return <Loading />;
  const d = board.data;
  const firstName = me.full_name?.trim().split(/\s+/)[0];
  const starting = d.getting_started.length > 0;

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-2xl font-bold text-brand-navy">
          Bonjour{firstName ? ` ${firstName}` : ""}
        </h1>
        <p className="mt-1 text-sm text-slate-600">
          {capitalize(today.format(new Date()))} · {me.org.name}
        </p>
      </div>

      {(d.actions.length > 0 || !starting) && <Actions actions={d.actions} />}
      {starting && <GettingStarted steps={d.getting_started} />}

      <Card
        title="Nouvelles annonces pour vous"
        actions={
          d.tenders_connected && d.new_tenders > 0 ? (
            <Badge tone="info">{d.new_tenders} cette semaine</Badge>
          ) : undefined
        }
      >
        {!d.tenders_connected ? (
          <p className="text-sm text-slate-600">
            La recherche automatique des annonces (BOAMP et TED) arrive bientôt.
            En attendant, créez un dossier à partir d&apos;un DCE reçu.
          </p>
        ) : d.best_tenders.length === 0 ? (
          <p className="text-sm text-slate-600">
            Aucune nouvelle annonce cette semaine pour vos métiers et vos
            départements.{" "}
            <Link
              href="/profil?onglet=veille"
              className="font-semibold text-brand-navy underline"
            >
              Régler la veille
            </Link>
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {d.best_tenders.map((t) => (
              <li
                key={t.tender_id}
                className="flex flex-wrap items-center gap-x-3 gap-y-1 py-3 sm:flex-nowrap"
              >
                <Badge tone={t.score != null && t.score >= 80 ? "ok" : "info"}>
                  {t.score == null ? "—" : `${t.score}/100`}
                </Badge>
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-slate-900">{t.title}</p>
                  <p className="text-xs text-slate-500">
                    {t.buyer_name ?? "Acheteur non précisé"}
                    {t.deadline_at &&
                      ` · avant le ${formatDateTime(t.deadline_at)}`}
                  </p>
                </div>
                <ButtonLink href="/annonces">Voir</ButtonLink>
              </li>
            ))}
          </ul>
        )}
        {d.tenders_connected && (
          <Link
            href="/annonces"
            className="mt-3 inline-block text-sm font-semibold text-brand-navy underline"
          >
            Toutes les annonces
          </Link>
        )}
      </Card>

      <Card
        title="Mes dossiers en cours"
        actions={
          <Link
            href="/dossiers"
            className="text-sm font-semibold text-brand-navy underline"
          >
            Tous les dossiers
          </Link>
        }
      >
        {d.bids.length === 0 ? (
          <p className="text-sm text-slate-600">
            Aucun dossier en cours.{" "}
            <Link
              href="/dossiers"
              className="font-semibold text-brand-navy underline"
            >
              Créer un dossier
            </Link>
          </p>
        ) : (
          <ul className="divide-y divide-slate-100">
            {d.bids.map((b) => (
              <BidRow key={b.id} bid={b} />
            ))}
          </ul>
        )}
      </Card>

      <Results d={d} />
    </div>
  );
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function ButtonLink({
  href,
  children,
}: {
  href: string;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="inline-flex shrink-0 items-center rounded-md bg-white px-3 py-1.5 text-sm font-semibold text-brand-navy ring-1 ring-inset ring-slate-300 hover:bg-slate-50"
    >
      {children}
    </Link>
  );
}

function Actions({ actions }: { actions: DashboardAction[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? actions : actions.slice(0, SHOWN);
  return (
    <Card title="À faire">
      {actions.length === 0 ? (
        <p className="flex items-center gap-2 text-sm font-medium text-emerald-800">
          <span aria-hidden="true">✓</span> Rien d&apos;urgent aujourd&apos;hui.
        </p>
      ) : (
        <>
          <ul className="divide-y divide-slate-100">
            {shown.map((a, i) => (
              <li
                key={`${a.href}-${a.title}-${i}`}
                className="flex flex-wrap items-center gap-x-3 gap-y-2 py-3 sm:flex-nowrap"
              >
                <span
                  className={`h-2.5 w-2.5 shrink-0 rounded-full ${LEVEL[a.level].dot}`}
                  aria-hidden="true"
                />
                <div className="min-w-0 flex-1">
                  <p className="font-medium text-slate-900">
                    <span className="sr-only">{LEVEL[a.level].label} : </span>
                    {a.title}
                  </p>
                  {a.detail && (
                    <p className="text-sm text-slate-600">{a.detail}</p>
                  )}
                </div>
                <ButtonLink href={a.href}>{a.button}</ButtonLink>
              </li>
            ))}
          </ul>
          {actions.length > SHOWN && (
            <button
              type="button"
              onClick={() => setAll((v) => !v)}
              className="mt-2 text-sm font-semibold text-brand-navy underline"
            >
              {all ? "Voir moins" : `Voir tout (${actions.length})`}
            </button>
          )}
        </>
      )}
    </Card>
  );
}

function GettingStarted({ steps }: { steps: DashboardStep[] }) {
  const done = steps.filter((s) => s.done).length;
  return (
    <Card
      title="Pour bien démarrer"
      actions={
        <span className="text-sm text-slate-600">
          {done} sur {steps.length}
        </span>
      }
    >
      <ol className="space-y-3">
        {steps.map((s, i) => (
          <li
            key={s.key}
            className="flex flex-wrap items-center gap-3 sm:flex-nowrap"
          >
            <span
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-semibold ${s.done ? "bg-brand-green text-brand-navy" : "bg-slate-100 text-slate-600"}`}
              aria-hidden="true"
            >
              {s.done ? "✓" : i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={`font-medium ${s.done ? "text-slate-500 line-through" : "text-slate-900"}`}
              >
                {s.title}
                {s.done && <span className="sr-only"> (fait)</span>}
              </p>
              {!s.done && <p className="text-sm text-slate-600">{s.detail}</p>}
            </div>
            {!s.done && <ButtonLink href={s.href}>Commencer</ButtonLink>}
          </li>
        ))}
      </ol>
    </Card>
  );
}

function daysLeft(iso: string): number {
  const fmt = (d: Date) =>
    new Intl.DateTimeFormat("en-CA", { timeZone: "Europe/Paris" }).format(d);
  const day = (s: string) => Date.parse(`${s}T00:00:00Z`);
  return Math.round((day(fmt(new Date(iso))) - day(fmt(new Date()))) / 864e5);
}

function Countdown({ bid }: { bid: BidProgress }) {
  if (bid.status === "submitted")
    return <Badge tone="info">Résultat attendu</Badge>;
  if (!bid.deadline_at) return null;
  const n = daysLeft(bid.deadline_at);
  if (n < 0) return <Badge tone="neutral">Date limite passée</Badge>;
  const tone = n <= 3 ? "danger" : n <= 10 ? "warning" : "neutral";
  return <Badge tone={tone}>{n === 0 ? "Aujourd'hui" : `J-${n}`}</Badge>;
}

function BidRow({ bid }: { bid: BidProgress }) {
  return (
    <li className="space-y-2 py-3">
      <div className="flex flex-wrap items-center gap-x-3 gap-y-1">
        <Link
          href={`/dossiers/${bid.id}`}
          className="font-medium text-brand-navy underline"
        >
          {bid.title}
        </Link>
        <Countdown bid={bid} />
        {bid.buyer_name && (
          <span className="text-sm text-slate-500">{bid.buyer_name}</span>
        )}
      </div>
      <ol
        className="flex flex-wrap items-center gap-1.5 text-xs"
        aria-label="Étapes du dossier"
      >
        {STAGES.map((s, i) => {
          const done = bid.done.includes(s.key);
          return (
            <li key={s.key} className="flex items-center gap-1.5">
              {i > 0 && (
                <span className="text-slate-300" aria-hidden="true">
                  ›
                </span>
              )}
              <span
                className={`rounded-full px-2 py-0.5 font-medium ${done ? "bg-emerald-50 text-emerald-800 ring-1 ring-inset ring-emerald-200" : "bg-slate-100 text-slate-500"}`}
              >
                {done && <span aria-hidden="true">✓ </span>}
                {s.label}
                <span className="sr-only">
                  {done ? " : fait" : " : à faire"}
                </span>
              </span>
            </li>
          );
        })}
      </ol>
      {bid.next_step && (
        <p className="text-sm text-slate-600">
          {bid.waiting ? "Pilao y travaille : " : "Prochaine étape : "}
          {bid.next_step.charAt(0).toLowerCase() + bid.next_step.slice(1)}
          {bid.waiting ? "…" : "."}
        </p>
      )}
    </li>
  );
}

function Results({ d }: { d: Dashboard }) {
  const r = d.results;
  const t = d.time_saved;
  if (r.deposited === 0 && t.bids === 0) return null;
  const plural = (n: number, word: string) => `${n} ${word}${n > 1 ? "s" : ""}`;
  const items: [string, string][] = [["Offres déposées", String(r.deposited)]];
  if (r.won + r.lost > 0) {
    // rate and amount only once a result is known: no « — » before that
    items.push(["Gagnées", String(r.won)]);
    items.push([
      "Taux de réussite",
      `${Math.round((r.success_rate ?? 0) * 100)} %`,
    ]);
    if (r.amount_won_cents)
      items.push(["Marchés gagnés", `${formatCents(r.amount_won_cents)} HT`]);
  } else if (r.submitted > 0) {
    items.push(["En attente du résultat", String(r.submitted)]);
  }
  if (t.bids > 0 && t.minutes_saved > 0)
    items.push(["Temps gagné", formatDuration(t.minutes_saved)]);
  return (
    <section aria-labelledby="results-title" className="space-y-2">
      <h2
        id="results-title"
        className="text-sm font-semibold uppercase tracking-wide text-slate-500"
      >
        Vos résultats
      </h2>
      <dl className="grid grid-cols-2 gap-3 sm:grid-cols-3 lg:grid-cols-5">
        {items.map(([label, value]) => (
          <div
            key={label}
            className="rounded-lg bg-white px-4 py-3 ring-1 ring-slate-200"
          >
            <dt className="text-xs text-slate-500">{label}</dt>
            <dd className="text-lg font-semibold text-brand-navy">{value}</dd>
          </div>
        ))}
      </dl>
      {t.bids > 0 && (
        <p className="text-xs text-slate-500">
          Temps gagné calculé sur {plural(t.bids, "dossier")} où vous
          l&apos;avez renseigné.
        </p>
      )}
    </section>
  );
}
