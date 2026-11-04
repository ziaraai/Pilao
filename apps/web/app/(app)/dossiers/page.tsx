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
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatDateTime, fromParisInput } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import { BID_STATUS } from "@/lib/labels";
import type { Bid } from "@/lib/types";

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
      />
      <Card title="Nouveau dossier">
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
        <Card>
          <ul className="divide-y divide-slate-100">
            {bids.data.map((b) => (
              <li key={b.id}>
                <Link
                  href={`/dossiers/${b.id}`}
                  className="flex flex-wrap items-center justify-between gap-3 py-3 hover:bg-slate-50"
                >
                  <div>
                    <p className="font-medium text-brand-navy">{b.title}</p>
                    <p className="text-xs text-slate-500">
                      {b.buyer_name ?? "Acheteur non renseigné"} · date limite :{" "}
                      {formatDateTime(b.deadline_at)}
                    </p>
                  </div>
                  <Badge
                    tone={
                      b.status === "won"
                        ? "ok"
                        : b.status === "lost" || b.status === "dropped"
                          ? "neutral"
                          : "info"
                    }
                  >
                    {BID_STATUS[b.status] ?? b.status}
                  </Badge>
                </Link>
              </li>
            ))}
          </ul>
        </Card>
      )}
    </div>
  );
}
