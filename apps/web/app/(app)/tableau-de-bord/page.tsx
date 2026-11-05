"use client";

import Link from "next/link";

import {
  Alert,
  Badge,
  Card,
  Empty,
  Loading,
  PageTitle,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDate, formatDateTime } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { BID_STATUS, VAULT_KINDS, VAULT_STATUS } from "@/lib/labels";
import type { Bid, Dashboard } from "@/lib/types";

const COLUMNS = [
  "to_review",
  "in_progress",
  "submitted",
  "won",
  "lost",
] as const;

/** US-5.3: what needs attention today, then the bids by status. */
export default function DashboardPage() {
  const board = useApi<Dashboard>("/dashboard");
  if (board.error && !board.data)
    return <Alert tone="danger">{board.error}</Alert>;
  if (!board.data) return <Loading />;
  const d = board.data;
  const rate = d.results.success_rate;
  return (
    <div className="space-y-6">
      <PageTitle
        title="Tableau de bord"
        subtitle="Nouvelles annonces, dates limites proches, attestations à renouveler et suivi de vos dossiers."
      />
      <div className="grid gap-4 md:grid-cols-4">
        <Stat
          label="Nouvelles annonces (7 jours)"
          value={String(d.new_tenders)}
          href="/annonces"
        />
        <Stat
          label="Dates limites dans 10 jours"
          value={String(d.deadlines_soon.length)}
        />
        <Stat
          label="Attestations à renouveler"
          value={String(d.documents_to_renew.length)}
          href="/coffre-fort"
        />
        <Stat
          label="Taux de réussite"
          value={rate == null ? "—" : `${Math.round(rate * 100)} %`}
          hint={`${d.results.won} gagné${d.results.won > 1 ? "s" : ""}, ${d.results.lost} perdu${d.results.lost > 1 ? "s" : ""}`}
        />
      </div>
      <div className="grid gap-6 lg:grid-cols-2">
        <Card title="Meilleures nouvelles annonces">
          {d.best_tenders.length === 0 ? (
            <Empty>Aucune nouvelle annonce cette semaine.</Empty>
          ) : (
            <ul className="divide-y divide-slate-100">
              {d.best_tenders.map((t) => (
                <li
                  key={t.tender_id}
                  className="flex items-start gap-3 py-2 text-sm"
                >
                  <Badge
                    tone={t.score != null && t.score >= 80 ? "ok" : "info"}
                  >
                    {t.score == null ? "—" : `${t.score}/100`}
                  </Badge>
                  <div>
                    <p className="font-medium">{t.title}</p>
                    <p className="text-xs text-slate-500">
                      {t.buyer_name ?? "Acheteur non précisé"} · date limite{" "}
                      {formatDateTime(t.deadline_at)}
                    </p>
                  </div>
                </li>
              ))}
            </ul>
          )}
          <Link
            href="/annonces"
            className="mt-3 inline-block text-sm text-brand-navy underline"
          >
            Toutes les annonces
          </Link>
        </Card>
        <Card title="À surveiller">
          {d.deadlines_soon.length === 0 &&
          d.documents_to_renew.length === 0 ? (
            <Empty>
              Rien d&apos;urgent : aucune date limite dans 10 jours,
              attestations à jour.
            </Empty>
          ) : (
            <ul className="space-y-2 text-sm">
              {d.deadlines_soon.map((b) => (
                <li key={b.id}>
                  <Link
                    href={`/dossiers/${b.id}`}
                    className="font-medium text-brand-navy underline"
                  >
                    {b.title}
                  </Link>{" "}
                  — date limite {formatDateTime(b.deadline_at)}
                </li>
              ))}
              {d.documents_to_renew.map((doc) => (
                <li key={doc.id} className="flex flex-wrap items-center gap-2">
                  <Badge tone={VAULT_STATUS[doc.status]?.tone ?? "warning"}>
                    {VAULT_STATUS[doc.status]?.label ?? doc.status}
                  </Badge>
                  {VAULT_KINDS[doc.kind] ?? doc.kind}
                  {doc.valid_until &&
                    ` — fin le ${formatDate(doc.valid_until)}`}
                </li>
              ))}
            </ul>
          )}
        </Card>
      </div>
      <section aria-labelledby="board-title" className="space-y-3">
        <h2 id="board-title" className="text-lg font-semibold text-brand-navy">
          Dossiers
        </h2>
        <div className="grid gap-3 md:grid-cols-3 xl:grid-cols-5">
          {COLUMNS.map((status) => (
            <div key={status} className="rounded-lg bg-slate-100 p-3">
              <h3 className="mb-2 text-sm font-semibold text-slate-700">
                {BID_STATUS[status]} ({d.bids_by_status[status]?.length ?? 0})
              </h3>
              <ul className="space-y-2">
                {(d.bids_by_status[status] ?? []).map((b) => (
                  <BidCard key={b.id} bid={b} onChange={board.reload} />
                ))}
              </ul>
            </div>
          ))}
        </div>
      </section>
    </div>
  );
}

function Stat({
  label,
  value,
  hint,
  href,
}: {
  label: string;
  value: string;
  hint?: string;
  href?: string;
}) {
  const body = (
    <div className="rounded-lg bg-white p-4 shadow-sm ring-1 ring-slate-200">
      <p className="text-2xl font-semibold text-brand-navy">{value}</p>
      <p className="text-sm text-slate-600">{label}</p>
      {hint && <p className="text-xs text-slate-500">{hint}</p>}
    </div>
  );
  return href ? <Link href={href}>{body}</Link> : body;
}

function BidCard({ bid, onChange }: { bid: Bid; onChange: () => void }) {
  const move = useAction();
  return (
    <li className="space-y-1 rounded-md bg-white p-2 text-sm shadow-sm">
      <Link
        href={`/dossiers/${bid.id}`}
        className="font-medium text-brand-navy underline"
      >
        {bid.title}
      </Link>
      {bid.deadline_at && (
        <p className="text-xs text-slate-500">
          Date limite {formatDateTime(bid.deadline_at)}
        </p>
      )}
      <label htmlFor={`move-${bid.id}`} className="sr-only">
        Statut de {bid.title}
      </label>
      <Select
        id={`move-${bid.id}`}
        value={bid.status}
        disabled={move.busy}
        className="py-1 text-xs"
        onChange={async (e) => {
          const ok = await move.run(() =>
            api(`/bids/${bid.id}`, {
              method: "PATCH",
              json: { status: e.target.value },
            }),
          );
          if (ok) onChange();
        }}
      >
        {Object.entries(BID_STATUS).map(([k, l]) => (
          <option key={k} value={k}>
            {l}
          </option>
        ))}
      </Select>
      {move.error && <Alert tone="danger">{move.error}</Alert>}
    </li>
  );
}
