"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  Alert,
  Badge,
  Card,
  type Color,
  Loading,
  tableHead,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { formatCents, formatDateTimeShort, formatDuration } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type {
  Bid,
  BidProgress,
  BidStage,
  Dashboard,
  DashboardAction,
  DashboardStep,
  TenderMatch,
  VaultSummary,
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
  todo: { dot: "bg-slate-400", label: "À faire" },
} as const;

/** The counters take the colour of their block (ADR-038). */
const TILE: Record<Color, string> = {
  red: "border-red-300 border-l-red-500 bg-red-100 text-red-700 hover:bg-red-200/70",
  green:
    "border-emerald-300 border-l-emerald-500 bg-emerald-100 text-emerald-700 hover:bg-emerald-200/70",
  blue: "border-blue-300 border-l-blue-500 bg-blue-100 text-blue-700 hover:bg-blue-200/70",
  amber:
    "border-amber-300 border-l-amber-500 bg-amber-100 text-amber-700 hover:bg-amber-200/70",
  brand: "border-emerald-300 border-l-brand-green bg-[#dcfbf1] text-brand-navy",
  violet: "border-violet-300 border-l-violet-500 bg-violet-100 text-violet-700",
  sky: "border-sky-300 border-l-sky-500 bg-sky-100 text-sky-700",
  slate:
    "border-slate-300 border-l-slate-400 bg-white text-slate-600 hover:bg-slate-50",
};
const ROW = "px-5 py-3 even:bg-slate-50";

const today = new Intl.DateTimeFormat("fr-FR", {
  weekday: "long",
  day: "numeric",
  month: "long",
  timeZone: "Europe/Paris",
});

/** US-5.3: counters, what to do now, the new notices, the bids in progress, the results. */
export default function DashboardPage() {
  const { me } = useMe();
  const board = useApi<Dashboard>("/dashboard");
  const vault = useApi<VaultSummary>("/vault/summary");
  if (board.error && !board.data)
    return <Alert tone="danger">{board.error}</Alert>;
  if (!board.data) return <Loading />;
  const d = board.data;
  const firstName = me.full_name?.trim().split(/\s+/)[0];
  const starting = d.getting_started.length > 0;
  const counts = vault.data?.counts ?? {};
  const urgent = d.actions.filter((a) => a.level === "urgent").length;
  const inProgress = d.bids.filter((b) => b.status !== "submitted").length;
  const toRenew =
    (counts.expired ?? 0) + (counts.mismatch ?? 0) + (counts.expiring ?? 0);

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

      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4 lg:gap-4">
        <Tile
          href="#a-faire"
          color={urgent ? "red" : "slate"}
          count={urgent}
          label={urgent > 1 ? "urgences à traiter" : "urgence à traiter"}
        />
        <Tile
          href="/annonces"
          color="green"
          count={d.new_tenders}
          label={d.new_tenders > 1 ? "nouvelles annonces" : "nouvelle annonce"}
        />
        <Tile
          href="/dossiers"
          color="blue"
          count={inProgress}
          label={inProgress > 1 ? "dossiers en cours" : "dossier en cours"}
        />
        <Tile
          href="/coffre-fort"
          color={toRenew ? "amber" : "slate"}
          count={toRenew}
          label={
            toRenew > 1
              ? "attestations à renouveler"
              : "attestation à renouveler"
          }
        />
      </div>

      {(d.actions.length > 0 || !starting) && <Actions actions={d.actions} />}
      {starting && <GettingStarted steps={d.getting_started} />}
      <Tenders d={d} />
      <Bids bids={d.bids} />
      <Results d={d} />
    </div>
  );
}

function capitalize(text: string): string {
  return text.charAt(0).toUpperCase() + text.slice(1);
}

function Tile({
  href,
  color,
  count,
  label,
}: {
  href: string;
  color: Color;
  count: number;
  label: string;
}) {
  return (
    <Link
      href={href}
      className={`flex items-center justify-between gap-2 rounded-lg border border-l-[6px] px-4 py-3 shadow-sm ${TILE[color]}`}
    >
      <span className="min-w-0">
        <span className="block text-3xl font-bold leading-tight">{count}</span>
        <span className="block text-sm font-medium text-slate-700">
          {label}
        </span>
      </span>
      <span className="text-2xl leading-none" aria-hidden="true">
        ›
      </span>
    </Link>
  );
}

/** Column titles above a list: the look of a table, the rows still stack on a phone. */
function Heads({ grid, labels }: { grid: string; labels: string[] }) {
  return (
    <div
      aria-hidden="true"
      className={`hidden gap-x-4 px-5 py-2 ${tableHead} ${grid}`}
    >
      {labels.map((l, i) => (
        <span key={i}>{l}</span>
      ))}
    </div>
  );
}

function PanelLink({ href, children }: { href: string; children: string }) {
  return (
    <Link href={href} className="text-sm font-semibold underline">
      {children}
    </Link>
  );
}

function Note({ children }: { children: React.ReactNode }) {
  return <p className="px-5 py-3 text-sm text-slate-600">{children}</p>;
}

function ButtonLink({
  href,
  primary,
  children,
}: {
  href: string;
  primary?: boolean;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className={`inline-flex shrink-0 items-center justify-center rounded-md px-3.5 py-1.5 text-sm font-semibold ${
        primary
          ? "bg-brand-navy text-white hover:bg-[#0a2a63]"
          : "bg-white text-brand-navy ring-1 ring-inset ring-slate-400 hover:bg-slate-50"
      }`}
    >
      {children}
    </Link>
  );
}

function Actions({ actions }: { actions: DashboardAction[] }) {
  const [all, setAll] = useState(false);
  const shown = all ? actions : actions.slice(0, SHOWN);
  return (
    <Card
      flush
      id="a-faire"
      color="red"
      icon="todo"
      title="À faire"
      actions={
        actions.length > SHOWN && (
          <button
            type="button"
            onClick={() => setAll((v) => !v)}
            className="text-sm font-semibold underline"
          >
            {all ? "Voir moins" : `Voir tout (${actions.length})`}
          </button>
        )
      }
    >
      {actions.length === 0 ? (
        <p className="flex items-center gap-2 px-5 py-3 text-sm font-medium text-emerald-800">
          <span aria-hidden="true">✓</span> Rien d&apos;urgent aujourd&apos;hui.
        </p>
      ) : (
        <ul className="divide-y divide-slate-200">
          {shown.map((a, i) => (
            <li
              key={`${a.href}-${a.title}-${i}`}
              className={`flex flex-wrap items-center gap-x-3 gap-y-2 sm:flex-nowrap ${ROW}`}
            >
              <span
                className={`h-2.5 w-2.5 shrink-0 rounded-full ${LEVEL[a.level].dot}`}
                aria-hidden="true"
              />
              <div className="min-w-0 flex-1">
                <p className="font-semibold text-slate-900">
                  <span className="sr-only">{LEVEL[a.level].label} : </span>
                  {a.title}
                </p>
                {a.detail && (
                  <p className="text-sm text-slate-600">{a.detail}</p>
                )}
              </div>
              <ButtonLink href={a.href} primary={a.level !== "todo"}>
                {a.button}
              </ButtonLink>
            </li>
          ))}
        </ul>
      )}
    </Card>
  );
}

function GettingStarted({ steps }: { steps: DashboardStep[] }) {
  const done = steps.filter((s) => s.done).length;
  return (
    <Card
      flush
      id="demarrer"
      color="brand"
      icon="start"
      title="Pour bien démarrer"
      actions={
        <span className="text-sm font-semibold">
          {done} sur {steps.length}
        </span>
      }
    >
      <ol className="divide-y divide-slate-200">
        {steps.map((s, i) => (
          <li
            key={s.key}
            className={`flex flex-wrap items-center gap-3 sm:flex-nowrap ${ROW}`}
          >
            <span
              className={`flex h-7 w-7 shrink-0 items-center justify-center rounded-full text-sm font-bold ${s.done ? "bg-brand-green text-brand-navy" : "bg-slate-200 text-slate-700"}`}
              aria-hidden="true"
            >
              {s.done ? "✓" : i + 1}
            </span>
            <div className="min-w-0 flex-1">
              <p
                className={`font-semibold ${s.done ? "text-slate-500 line-through" : "text-slate-900"}`}
              >
                {s.title}
                {s.done && <span className="sr-only"> (fait)</span>}
              </p>
              {!s.done && <p className="text-sm text-slate-600">{s.detail}</p>}
            </div>
            {!s.done && (
              <ButtonLink href={s.href} primary>
                Commencer
              </ButtonLink>
            )}
          </li>
        ))}
      </ol>
    </Card>
  );
}

// fixed side columns: every row is its own grid, the column titles must line up
const TENDER_GRID = "md:grid md:grid-cols-[4.5rem_minmax(0,1fr)_9.5rem_9.5rem]";

function Tenders({ d }: { d: Dashboard }) {
  return (
    <Card
      flush
      id="annonces"
      color="green"
      icon="tenders"
      title="Nouvelles annonces pour vous"
      actions={
        d.tenders_connected && (
          <span className="flex flex-wrap items-center gap-x-4 gap-y-1">
            {d.new_tenders > 0 && (
              <span className="text-sm font-semibold">
                {d.new_tenders} cette semaine
              </span>
            )}
            <PanelLink href="/annonces">Toutes les annonces</PanelLink>
          </span>
        )
      }
    >
      {!d.tenders_connected ? (
        <Note>
          La recherche automatique des annonces (BOAMP et TED) arrive bientôt.
          En attendant, créez un dossier à partir d&apos;un DCE reçu.
        </Note>
      ) : d.best_tenders.length === 0 ? (
        <Note>
          Aucune nouvelle annonce cette semaine pour vos métiers et vos
          départements.{" "}
          <Link
            href="/profil?onglet=veille"
            className="font-semibold text-brand-navy underline"
          >
            Régler la veille
          </Link>
        </Note>
      ) : (
        <>
          <Heads
            grid={TENDER_GRID}
            labels={["Score", "Annonce", "Date limite", ""]}
          />
          <ul className="divide-y divide-slate-200">
            {d.best_tenders.map((t) => (
              <TenderRow key={t.tender_id} tender={t} />
            ))}
          </ul>
        </>
      )}
    </Card>
  );
}

function Score({ score }: { score: number | null }) {
  const tone =
    score == null
      ? "bg-slate-100 text-slate-600 ring-slate-300"
      : score >= 80
        ? "bg-emerald-100 text-emerald-800 ring-emerald-300"
        : score >= 60
          ? "bg-blue-100 text-blue-800 ring-blue-300"
          : "bg-slate-100 text-slate-700 ring-slate-300";
  return (
    <span
      className={`inline-flex min-w-11 justify-center justify-self-start rounded-md px-2 py-1 text-sm font-bold ring-1 ring-inset ${tone}`}
    >
      {score ?? "—"}
      <span className="sr-only"> sur 100</span>
    </span>
  );
}

function TenderRow({ tender: t }: { tender: TenderMatch }) {
  const router = useRouter();
  const track = useAction();
  const meta = [
    t.buyer_name ?? "Acheteur non précisé",
    t.departments.join(", "),
    t.estimated_amount_cents != null
      ? `${formatCents(t.estimated_amount_cents)} HT`
      : "",
    t.source.toUpperCase(),
  ].filter(Boolean);
  return (
    <li
      className={`flex flex-wrap items-center gap-x-3 gap-y-2 md:gap-x-4 ${TENDER_GRID} ${ROW}`}
    >
      <Score score={t.score} />
      <div className="min-w-0 flex-1">
        <p className="font-semibold text-slate-900">{t.title}</p>
        <p className="text-sm text-slate-600">{meta.join(" · ")}</p>
        {track.error && (
          <p className="text-sm text-red-700" role="alert">
            {track.error}
          </p>
        )}
      </div>
      <p className="w-full text-sm text-slate-800 md:w-auto">
        <span className="md:hidden">Date limite : </span>
        {formatDateTimeShort(t.deadline_at)}
      </p>
      <div className="flex gap-2 md:justify-end">
        <ButtonLink href="/annonces">Voir</ButtonLink>
        <button
          type="button"
          disabled={track.busy}
          aria-busy={track.busy || undefined}
          onClick={async () => {
            const bid = await track.run(() =>
              api<Bid>(`/tenders/${t.tender_id}/track`, { method: "POST" }),
            );
            if (bid) router.push(`/dossiers/${bid.id}`);
          }}
          className="inline-flex shrink-0 items-center rounded-md bg-brand-navy px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-[#0a2a63] disabled:opacity-50"
        >
          Suivre
        </button>
      </div>
    </li>
  );
}

const BID_GRID = "xl:grid xl:grid-cols-[minmax(0,1fr)_9rem_20rem_7.5rem]";

function Bids({ bids }: { bids: BidProgress[] }) {
  return (
    <Card
      flush
      id="dossiers"
      color="blue"
      icon="bids"
      title="Mes dossiers en cours"
      actions={<PanelLink href="/dossiers">Tous les dossiers</PanelLink>}
    >
      {bids.length === 0 ? (
        <Note>
          Aucun dossier en cours.{" "}
          <Link
            href="/dossiers"
            className="font-semibold text-brand-navy underline"
          >
            Créer un dossier
          </Link>
        </Note>
      ) : (
        <>
          <Heads
            grid={BID_GRID}
            labels={["Dossier", "Date limite", "Avancement", ""]}
          />
          <ul className="divide-y divide-slate-200">
            {bids.map((b) => (
              <BidRow key={b.id} bid={b} />
            ))}
          </ul>
        </>
      )}
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
  const submitted = bid.status === "submitted";
  const current = submitted
    ? null
    : STAGES.find((s) => !bid.done.includes(s.key))?.key;
  return (
    <li className={`grid gap-x-4 gap-y-2 xl:items-center ${BID_GRID} ${ROW}`}>
      <div className="min-w-0">
        <Link
          href={`/dossiers/${bid.id}`}
          className="font-semibold text-brand-navy underline"
        >
          {bid.title}
        </Link>
        {bid.buyer_name && (
          <p className="text-sm text-slate-600">{bid.buyer_name}</p>
        )}
        {bid.next_step && (
          <p className="text-sm text-slate-600">
            {bid.waiting ? "Pilao y travaille : " : "Prochaine étape : "}
            {bid.next_step.charAt(0).toLowerCase() + bid.next_step.slice(1)}
            {bid.waiting ? "…" : "."}
          </p>
        )}
      </div>
      <div className="flex flex-wrap items-center gap-x-2 xl:block">
        <Countdown bid={bid} />
        {bid.deadline_at && !submitted && (
          <p className="text-xs text-slate-600 xl:mt-1">
            {formatDateTimeShort(bid.deadline_at)}
          </p>
        )}
      </div>
      <ol
        className="flex flex-wrap items-center gap-1.5 text-xs"
        aria-label="Étapes du dossier"
      >
        {STAGES.map((s, i) => {
          const done = bid.done.includes(s.key);
          const next = s.key === current;
          return (
            <li key={s.key} className="flex items-center gap-1.5">
              {i > 0 && (
                <span className="text-slate-400" aria-hidden="true">
                  ›
                </span>
              )}
              <span
                className={`rounded-full px-2 py-0.5 font-semibold ring-1 ring-inset ${
                  done
                    ? "bg-emerald-100 text-emerald-800 ring-emerald-300"
                    : next
                      ? "bg-amber-100 text-amber-900 ring-amber-300"
                      : "bg-slate-100 text-slate-500 ring-slate-200"
                }`}
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
      <div className="xl:text-right">
        <ButtonLink href={`/dossiers/${bid.id}`} primary={!submitted}>
          {submitted ? "Ouvrir" : "Continuer"}
        </ButtonLink>
      </div>
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
    <Card
      flush
      id="resultats"
      color="violet"
      icon="results"
      title="Vos résultats"
    >
      <dl className="grid grid-cols-2 gap-3 p-5 sm:grid-cols-3 lg:grid-cols-5">
        {items.map(([label, value]) => (
          <div
            key={label}
            className="rounded-md border border-violet-200 bg-violet-50 px-4 py-3"
          >
            <dt className="text-xs font-medium text-slate-600">{label}</dt>
            <dd className="text-lg font-bold text-brand-navy">{value}</dd>
          </div>
        ))}
      </dl>
      {t.bids > 0 && (
        <p className="px-5 pb-3 text-xs text-slate-600">
          Temps gagné calculé sur {plural(t.bids, "dossier")} où vous
          l&apos;avez renseigné.
        </p>
      )}
    </Card>
  );
}
