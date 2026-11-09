"use client";

import Link from "next/link";
import { useRouter } from "next/navigation";
import { useState } from "react";

import {
  Alert,
  Button,
  Card,
  Empty,
  Field,
  Input,
  Loading,
  PageTitle,
  tableHead,
  tableRow,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTimeShort, fromParisInput } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { BID_STATUS } from "@/lib/labels";
import type { Bid } from "@/lib/types";

const GRID = "md:grid-cols-[minmax(0,1fr)_9.5rem_7rem_6rem]";
const STATUS_COLOR: Record<string, string> = {
  to_review: "bg-slate-100 text-slate-700 ring-slate-300",
  in_progress: "bg-blue-100 text-blue-800 ring-blue-300",
  submitted: "bg-violet-100 text-violet-800 ring-violet-300",
  won: "bg-emerald-100 text-emerald-800 ring-emerald-300",
  lost: "bg-red-50 text-red-800 ring-red-200",
  dropped: "bg-slate-100 text-slate-500 ring-slate-200",
};

export default function BidsPage() {
  const router = useRouter();
  const bids = useApi<Bid[]>("/bids");
  const [form, setForm] = useState({ title: "", buyer_name: "", deadline: "" });
  const create = useAction();

  async function onCreate(e: React.FormEvent) {
    e.preventDefault();
    const bid = await create.run(() =>
      api<Bid>("/bids", {
        json: {
          title: form.title,
          buyer_name: form.buyer_name || null,
          deadline_at: fromParisInput(form.deadline),
        },
      }),
    );
    if (bid) router.push(`/dossiers/${bid.id}`);
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Dossiers de réponse"
        subtitle="Un dossier par appel d'offres : déposez le DCE, lisez l'analyse, préparez votre réponse."
        icon="bids"
        color="blue"
      />
      <Card title="Nouveau dossier" color="blue">
        <form
          onSubmit={onCreate}
          className="grid items-end gap-3 sm:grid-cols-[2fr_1.5fr_1fr_auto]"
          noValidate
        >
          <Field label="Intitulé" htmlFor="bid-title">
            <Input
              id="bid-title"
              value={form.title}
              onChange={(e) => setForm({ ...form, title: e.target.value })}
              placeholder="ex. Nettoyage des écoles de Lyon"
            />
          </Field>
          <Field label="Acheteur" htmlFor="bid-buyer">
            <Input
              id="bid-buyer"
              value={form.buyer_name}
              onChange={(e) => setForm({ ...form, buyer_name: e.target.value })}
            />
          </Field>
          <Field label="Date limite (heure de Paris)" htmlFor="bid-deadline">
            <Input
              id="bid-deadline"
              type="datetime-local"
              value={form.deadline}
              onChange={(e) => setForm({ ...form, deadline: e.target.value })}
            />
          </Field>
          <Button type="submit" busy={create.busy}>
            Créer
          </Button>
        </form>
        <p className="mt-2 text-xs text-slate-500">
          L&apos;acheteur et la date limite seront repris du DCE s&apos;ils sont
          laissés vides.
        </p>
        {create.error && (
          <div className="mt-3">
            <Alert tone="danger">{create.error}</Alert>
          </div>
        )}
      </Card>
      {bids.error && <Alert tone="danger">{bids.error}</Alert>}
      {!bids.data ? (
        <Loading />
      ) : bids.data.length === 0 ? (
        <Empty>
          Aucun dossier : créez-en un pour déposer votre premier DCE.
        </Empty>
      ) : (
        <Card
          title={`Mes dossiers (${bids.data.length})`}
          color="blue"
          icon="bids"
          flush
        >
          <div
            aria-hidden="true"
            className={`hidden gap-x-4 px-5 py-2 md:grid ${GRID} ${tableHead}`}
          >
            <span>Dossier</span>
            <span>Date limite</span>
            <span>Statut</span>
            <span />
          </div>
          <ul>
            {bids.data.map((b) => (
              <li
                key={b.id}
                className={`grid items-center gap-x-4 gap-y-1 px-5 py-3 md:grid ${GRID} ${tableRow}`}
              >
                <div className="min-w-0">
                  <Link
                    href={`/dossiers/${b.id}`}
                    className="font-semibold text-brand-navy underline"
                  >
                    {b.title}
                  </Link>
                  <p className="text-sm text-slate-600">
                    {b.buyer_name ?? "Acheteur non renseigné"}
                  </p>
                </div>
                <p className="text-sm text-slate-800">
                  <span className="md:hidden">Date limite : </span>
                  {formatDateTimeShort(b.deadline_at)}
                </p>
                <div>
                  <span
                    className={`inline-flex rounded-full px-2.5 py-0.5 text-xs font-semibold ring-1 ring-inset ${STATUS_COLOR[b.status] ?? STATUS_COLOR.to_review}`}
                  >
                    {BID_STATUS[b.status] ?? b.status}
                  </span>
                </div>
                <div className="md:text-right">
                  <Link
                    href={`/dossiers/${b.id}`}
                    aria-label={`Ouvrir le dossier ${b.title}`}
                    className="inline-flex rounded-md bg-brand-navy px-3.5 py-1.5 text-sm font-semibold text-white hover:bg-[#0a2a63]"
                  >
                    Ouvrir
                  </Link>
                </div>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
