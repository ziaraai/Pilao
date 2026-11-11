"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Empty,
  Field,
  Input,
  Loading,
  PageTitle,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import { useMe } from "@/lib/auth";
import { formatCents, formatDateTime, parseEuros } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { hasModule } from "@/lib/modules";
import type { Tone } from "@/lib/labels";
import type { TenderList, TenderMatch, Trade, TrackOut } from "@/lib/types";

type Status = TenderMatch["status"];
const TABS: { status: Status; label: string }[] = [
  { status: "new", label: "À traiter" },
  { status: "tracked", label: "Suivies" },
  { status: "dismissed", label: "Écartées" },
];
const REASONS = [
  "Hors de notre zone",
  "Pas notre métier",
  "Trop gros pour nous",
  "Trop petit",
  "Délai trop court",
];
const PER_PAGE = 50;

type Filters = {
  q: string;
  department: string;
  procedure: string;
  trade: string;
  minScore: string;
  deadlineBefore: string;
  minAmount: string;
  maxAmount: string;
};
const EMPTY: Filters = {
  q: "",
  department: "",
  procedure: "",
  trade: "",
  minScore: "",
  deadlineBefore: "",
  minAmount: "",
  maxAmount: "",
};

function query(status: Status, f: Filters, page: number): string {
  const p = new URLSearchParams({
    status,
    page: String(page),
    per_page: String(PER_PAGE),
  });
  if (f.q.trim()) p.set("q", f.q.trim());
  if (f.department) p.set("department", f.department);
  if (f.procedure) p.set("procedure", f.procedure);
  if (f.trade) p.set("trade", f.trade);
  if (f.minScore) p.set("min_score", f.minScore);
  if (f.deadlineBefore) p.set("deadline_before", f.deadlineBefore);
  const min = parseEuros(f.minAmount);
  const max = parseEuros(f.maxAmount);
  if (min != null) p.set("min_amount_cents", String(min));
  if (max != null) p.set("max_amount_cents", String(max));
  return `/tenders?${p}`;
}

function scoreTone(score: number): Tone {
  return score >= 80 ? "ok" : score >= 60 ? "info" : "neutral";
}

const SCORE_BOX: Partial<Record<Tone, string>> = {
  ok: "bg-emerald-100 text-emerald-800 ring-emerald-300",
  info: "bg-blue-100 text-blue-800 ring-blue-300",
  neutral: "bg-slate-100 text-slate-700 ring-slate-300",
};

/** The stripe on the left of a notice: green good match, blue possible, grey weak. */
function scoreStripe(score: number | null): string {
  if (score == null) return "border-l-slate-300";
  return score >= 80
    ? "border-l-emerald-500"
    : score >= 60
      ? "border-l-blue-500"
      : "border-l-slate-400";
}

function daysLeft(iso: string | null): string | null {
  if (!iso) return null;
  const days = Math.ceil((new Date(iso).getTime() - Date.now()) / 86_400_000);
  if (days < 0) return "clôturée";
  return days === 0 ? "aujourd'hui" : `dans ${days} jour${days > 1 ? "s" : ""}`;
}

/** US-2.2 / US-2.3: the notices that match the profile, scored, with their actions. */
export default function TendersPage() {
  const [status, setStatus] = useState<Status>("new");
  const [draft, setDraft] = useState<Filters>(EMPTY);
  const [filters, setFilters] = useState<Filters>(EMPTY);
  const [page, setPage] = useState(1);
  const list = useApi<TenderList>(query(status, filters, page));
  const trades = useApi<Trade[]>("/profile/trades");
  const set = (key: keyof Filters) => (e: { target: { value: string } }) =>
    setDraft((d) => ({ ...d, [key]: e.target.value }));

  return (
    <div className="space-y-6">
      <PageTitle
        title="Annonces"
        subtitle="Les appels d'offres qui correspondent à votre profil, avec un score et son explication."
        icon="tenders"
        color="green"
      />
      <div
        role="tablist"
        aria-label="Statut des annonces"
        className="flex gap-2"
      >
        {TABS.map((t) => (
          <Button
            key={t.status}
            role="tab"
            aria-selected={status === t.status}
            variant={status === t.status ? "primary" : "secondary"}
            onClick={() => {
              setStatus(t.status);
              setPage(1);
            }}
          >
            {t.label}
          </Button>
        ))}
      </div>
      <Card title="Filtres" color="slate">
        <form
          className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4"
          onSubmit={(e) => {
            e.preventDefault();
            setFilters(draft);
            setPage(1);
          }}
        >
          <Field label="Recherche" htmlFor="f-q">
            <Input
              id="f-q"
              value={draft.q}
              onChange={set("q")}
              placeholder="Objet ou acheteur"
            />
          </Field>
          <Field label="Secteur" htmlFor="f-trade">
            <Select id="f-trade" value={draft.trade} onChange={set("trade")}>
              <option value="">Tous</option>
              {trades.data?.map((t) => (
                <option key={t.code} value={t.code}>
                  {t.label}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Département" htmlFor="f-dep">
            <Select
              id="f-dep"
              value={draft.department}
              onChange={set("department")}
            >
              <option value="">Tous</option>
              {list.data?.departments.map((d) => (
                <option key={d} value={d}>
                  {d}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Procédure" htmlFor="f-proc">
            <Select
              id="f-proc"
              value={draft.procedure}
              onChange={set("procedure")}
            >
              <option value="">Toutes</option>
              {list.data?.procedures.map((p) => (
                <option key={p} value={p}>
                  {p}
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Score minimum" htmlFor="f-score">
            <Select
              id="f-score"
              value={draft.minScore}
              onChange={set("minScore")}
            >
              <option value="">Aucun</option>
              {[40, 60, 80].map((s) => (
                <option key={s} value={s}>
                  {s} / 100
                </option>
              ))}
            </Select>
          </Field>
          <Field label="Date limite avant le" htmlFor="f-deadline">
            <Input
              id="f-deadline"
              type="date"
              value={draft.deadlineBefore}
              onChange={set("deadlineBefore")}
            />
          </Field>
          <Field label="Montant minimum (€ HT)" htmlFor="f-min">
            <Input
              id="f-min"
              inputMode="decimal"
              value={draft.minAmount}
              onChange={set("minAmount")}
            />
          </Field>
          <Field label="Montant maximum (€ HT)" htmlFor="f-max">
            <Input
              id="f-max"
              inputMode="decimal"
              value={draft.maxAmount}
              onChange={set("maxAmount")}
            />
          </Field>
          <div className="flex gap-2 sm:col-span-2 lg:col-span-4">
            <Button type="submit">Filtrer</Button>
            <Button
              type="button"
              variant="ghost"
              onClick={() => {
                setDraft(EMPTY);
                setFilters(EMPTY);
                setPage(1);
              }}
            >
              Effacer les filtres
            </Button>
          </div>
        </form>
      </Card>
      {list.error && <Alert tone="danger">{list.error}</Alert>}
      {!list.data ? (
        <Loading />
      ) : list.data.items.length === 0 ? (
        <Empty>
          {status === "new"
            ? "Aucune annonce ne correspond pour l'instant. Vérifiez vos codes CPV, mots-clés et départements dans le profil."
            : status === "tracked"
              ? "Vous ne suivez aucune annonce."
              : "Aucune annonce écartée."}
        </Empty>
      ) : (
        <>
          <p className="text-sm text-slate-600" aria-live="polite">
            {list.data.total} annonce{list.data.total > 1 ? "s" : ""}, les mieux
            notées d&apos;abord.
          </p>
          <ul className="space-y-3">
            {list.data.items.map((t) => (
              <TenderCard key={t.tender_id} tender={t} onChange={list.reload} />
            ))}
          </ul>
          {list.data.total > PER_PAGE && (
            <div className="flex items-center gap-3">
              <Button
                variant="secondary"
                disabled={page === 1}
                onClick={() => setPage(page - 1)}
              >
                Page précédente
              </Button>
              <span className="text-sm text-slate-600">
                Page {page} sur {Math.ceil(list.data.total / PER_PAGE)}
              </span>
              <Button
                variant="secondary"
                disabled={page * PER_PAGE >= list.data.total}
                onClick={() => setPage(page + 1)}
              >
                Page suivante
              </Button>
            </div>
          )}
        </>
      )}
    </div>
  );
}

function TenderCard({
  tender: t,
  onChange,
}: {
  tender: TenderMatch;
  onChange: () => void;
}) {
  const router = useRouter();
  const { me } = useMe();
  const answers = hasModule(me.modules, "reponse"); // without it, « Suivre » makes no bid
  const [dismissing, setDismissing] = useState(false);
  const [reason, setReason] = useState(REASONS[0]);
  const [other, setOther] = useState("");
  const action = useAction();
  const left = daysLeft(t.deadline_at);
  return (
    <li
      className={`space-y-3 rounded-lg border border-slate-300 border-l-[6px] bg-white p-4 shadow-sm ${scoreStripe(t.score)}`}
    >
      <div className="flex flex-wrap items-start gap-3">
        <div className="min-w-64 flex-1">
          <h2 className="text-base font-semibold text-brand-navy">{t.title}</h2>
          <p className="text-sm text-slate-600">
            {t.buyer_name ?? "Acheteur non précisé"}
            {t.departments.length > 0 && ` · ${t.departments.join(", ")}`}
            {t.procedure && ` · ${t.procedure}`}
          </p>
        </div>
        {t.score != null ? (
          <span
            className={`inline-flex items-center rounded-md px-2.5 py-1 text-sm font-bold ring-1 ring-inset ${SCORE_BOX[scoreTone(t.score)]}`}
          >
            {t.score} / 100
          </span>
        ) : (
          <Badge tone="neutral">
            {t.score_error ? "Score indisponible" : "Score en attente"}
          </Badge>
        )}
      </div>
      {t.explanation && (
        <p className="text-sm text-slate-800">{t.explanation}</p>
      )}
      <dl className="grid gap-px overflow-hidden rounded-md border border-slate-300 bg-slate-300 text-sm sm:grid-cols-[minmax(0,2fr)_minmax(0,1.3fr)_minmax(0,0.7fr)]">
        <div className="bg-slate-50 px-3 py-2">
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">
            Date limite
          </dt>
          <dd className="font-medium text-slate-900">
            {formatDateTime(t.deadline_at)}
            {left && ` (${left})`}
          </dd>
        </div>
        <div className="bg-slate-50 px-3 py-2">
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">
            Montant estimé
          </dt>
          <dd className="font-medium text-slate-900">
            {t.estimated_amount_cents != null
              ? `${formatCents(t.estimated_amount_cents)} HT`
              : "Non précisé"}
          </dd>
        </div>
        <div className="bg-slate-50 px-3 py-2">
          <dt className="text-xs font-semibold uppercase tracking-wide text-slate-600">
            Source
          </dt>
          <dd className="font-medium text-slate-900">
            {t.source === "ted" ? "TED" : "BOAMP"}
          </dd>
        </div>
      </dl>
      {t.reasons.length > 0 && (
        <p className="flex flex-wrap gap-1.5 text-xs">
          {t.reasons.map((r) => (
            <span
              key={r}
              className="rounded-full bg-emerald-50 px-2 py-0.5 text-emerald-900 ring-1 ring-inset ring-emerald-200"
            >
              {r}
            </span>
          ))}
        </p>
      )}
      {t.corrections.length > 0 && (
        <Alert tone="warning">
          Avis rectificatif :{" "}
          {Object.entries(t.corrections[t.corrections.length - 1].changes)
            .map(([what, [from, to]]) => `${what} ${from} → ${to}`)
            .join(" ; ")}
        </Alert>
      )}
      {t.dismiss_reason && (
        <p className="text-xs text-slate-500">Écartée : {t.dismiss_reason}</p>
      )}
      <div className="flex flex-wrap gap-2">
        {t.notice_url && (
          <a
            href={t.notice_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md px-3 py-1.5 text-sm font-semibold text-brand-navy ring-1 ring-slate-300 hover:bg-slate-50"
          >
            Voir l&apos;annonce
          </a>
        )}
        {t.documents_url && (
          <a
            href={t.documents_url}
            target="_blank"
            rel="noopener noreferrer"
            className="rounded-md px-3 py-1.5 text-sm font-semibold text-brand-navy ring-1 ring-slate-300 hover:bg-slate-50"
          >
            Dossier de consultation
          </a>
        )}
        {t.status === "tracked" && !answers ? (
          <span className="rounded-md bg-emerald-100 px-3 py-1.5 text-sm font-semibold text-emerald-800 ring-1 ring-inset ring-emerald-300">
            Suivie
          </span>
        ) : t.status === "tracked" && t.bid_id ? (
          <Link
            href={`/dossiers/${t.bid_id}`}
            className="rounded-md bg-brand-navy px-3 py-1.5 text-sm font-semibold text-white"
          >
            Ouvrir le dossier
          </Link>
        ) : t.status === "dismissed" ? (
          <Button
            variant="secondary"
            busy={action.busy}
            onClick={async () => {
              const ok = await action.run(() =>
                api(`/tenders/${t.tender_id}/restore`, { method: "POST" }),
              );
              if (ok) onChange();
            }}
          >
            Remettre dans la liste
          </Button>
        ) : (
          <>
            <Button
              busy={action.busy}
              onClick={async () => {
                const res = await action.run(() =>
                  api<TrackOut>(`/tenders/${t.tender_id}/track`, {
                    method: "POST",
                  }),
                );
                if (res?.bid) router.push(`/dossiers/${res.bid.id}`);
                else if (res) onChange(); // followed, without a bid
              }}
            >
              Suivre
            </Button>
            <Button variant="ghost" onClick={() => setDismissing(!dismissing)}>
              Écarter
            </Button>
          </>
        )}
      </div>
      {dismissing && (
        <form
          className="flex flex-wrap items-end gap-2"
          onSubmit={async (e) => {
            e.preventDefault();
            const why = reason === "Autre" ? other.trim() : reason;
            if (!why) return;
            const ok = await action.run(() =>
              api(`/tenders/${t.tender_id}/dismiss`, { json: { reason: why } }),
            );
            if (ok) onChange();
          }}
        >
          <Field label="Raison" htmlFor={`why-${t.tender_id}`}>
            <Select
              id={`why-${t.tender_id}`}
              value={reason}
              onChange={(e) => setReason(e.target.value)}
              className="w-auto"
            >
              {[...REASONS, "Autre"].map((r) => (
                <option key={r}>{r}</option>
              ))}
            </Select>
          </Field>
          {reason === "Autre" && (
            <Field label="Précisez" htmlFor={`other-${t.tender_id}`}>
              <Input
                id={`other-${t.tender_id}`}
                value={other}
                maxLength={300}
                onChange={(e) => setOther(e.target.value)}
              />
            </Field>
          )}
          <Button type="submit" variant="secondary" busy={action.busy}>
            Confirmer
          </Button>
        </form>
      )}
      {action.error && <Alert tone="danger">{action.error}</Alert>}
    </li>
  );
}
