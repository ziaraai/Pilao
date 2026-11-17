"use client";

import { useState } from "react";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import type { TabId } from "@/lib/dossier";
import { formatDateTime, fromParisInput, toParisInput } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Bid, QuoteState } from "@/lib/types";

/**
 * The overview of a consultation (ADR-052): who asks, how to reach them, and the three steps
 * of the quote (documents received, prices, quote).
 */
export function ConsultationOverview({
  bid,
  quote,
  onOpen,
  onSaved,
}: {
  bid: Bid;
  quote: QuoteState | undefined;
  onOpen: (tab: TabId) => void;
  onSaved: (b: Bid) => void;
}) {
  const [editing, setEditing] = useState(false);
  const steps: { tab: TabId; label: string; state: string; done: boolean }[] = [
    {
      tab: "dce",
      label: "Documents reçus",
      state: bid.progress?.dce_ready
        ? "Déposés et lus."
        : "Déposez les pièces reçues par e-mail.",
      done: !!bid.progress?.dce_ready,
    },
    {
      tab: "prix",
      label: "Prix",
      state:
        quote?.blocking ?? "Tous les prix des rubriques retenues sont saisis.",
      done: !!quote && !quote.blocking,
    },
    {
      tab: "devis",
      label: "Devis",
      state:
        quote?.quote?.status === "ready"
          ? `Devis n° ${quote.quote.number} prêt.`
          : "À préparer quand les prix sont saisis.",
      done: quote?.quote?.status === "ready",
    },
  ];

  return (
    <div className="space-y-6">
      <Card
        title="La consultation"
        color="blue"
        icon="bids"
        actions={
          !editing && (
            <Button variant="secondary" onClick={() => setEditing(true)}>
              Modifier
            </Button>
          )
        }
      >
        {editing ? (
          <ConsultationForm
            bid={bid}
            onDone={(b) => {
              setEditing(false);
              if (b) onSaved(b);
            }}
          />
        ) : (
          <dl className="grid gap-x-6 gap-y-1 text-sm sm:grid-cols-[auto_1fr]">
            <dt className="text-slate-600">Client</dt>
            <dd>{bid.buyer_name ?? "à préciser"}</dd>
            <dt className="text-slate-600">Contact</dt>
            <dd>
              {bid.contact_name ?? "—"}
              {bid.contact_email && (
                <>
                  {" · "}
                  <a
                    className="text-brand-navy underline"
                    href={`mailto:${bid.contact_email}`}
                  >
                    {bid.contact_email}
                  </a>
                </>
              )}
            </dd>
            <dt className="text-slate-600">Lot ou référence</dt>
            <dd>{bid.lot_label ?? bid.reference ?? "—"}</dd>
            <dt className="text-slate-600">Devis à remettre le</dt>
            <dd>{formatDateTime(bid.deadline_at)}</dd>
          </dl>
        )}
      </Card>
      <Card title="Étapes du devis" color="green" icon="todo">
        <ol className="space-y-3">
          {steps.map((s, i) => (
            <li
              key={s.tab}
              className="flex flex-wrap items-center justify-between gap-3"
            >
              <div>
                <p className="text-sm font-semibold text-slate-900">
                  {s.done ? "✓ " : `${i + 1}. `}
                  {s.label}
                </p>
                <p className="text-sm text-slate-600">{s.state}</p>
              </div>
              <Button variant="secondary" onClick={() => onOpen(s.tab)}>
                Ouvrir
              </Button>
            </li>
          ))}
        </ol>
      </Card>
    </div>
  );
}

function ConsultationForm({
  bid,
  onDone,
}: {
  bid: Bid;
  onDone: (b: Bid | null) => void;
}) {
  const [form, setForm] = useState({
    buyer_name: bid.buyer_name ?? "",
    contact_name: bid.contact_name ?? "",
    contact_email: bid.contact_email ?? "",
    lot_label: bid.lot_label ?? "",
    deadline: toParisInput(bid.deadline_at),
  });
  const save = useAction();
  const set =
    (k: keyof typeof form) => (e: React.ChangeEvent<HTMLInputElement>) =>
      setForm({ ...form, [k]: e.target.value });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const next = await save.run(() =>
      api<Bid>(`/bids/${bid.id}`, {
        method: "PATCH",
        json: {
          buyer_name: form.buyer_name.trim() || null,
          contact_name: form.contact_name.trim() || null,
          contact_email: form.contact_email.trim() || null,
          lot_label: form.lot_label.trim() || null,
          deadline_at: fromParisInput(form.deadline),
        },
      }),
    );
    if (next) onDone(next);
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-3">
      <div className="grid gap-3 sm:grid-cols-2">
        <Field label="Client (entreprise qui consulte)" htmlFor="c-client">
          <Input
            id="c-client"
            value={form.buyer_name}
            onChange={set("buyer_name")}
          />
        </Field>
        <Field label="Lot ou référence" htmlFor="c-lot">
          <Input
            id="c-lot"
            value={form.lot_label}
            onChange={set("lot_label")}
          />
        </Field>
        <Field label="Contact (nom)" htmlFor="c-contact">
          <Input
            id="c-contact"
            value={form.contact_name}
            onChange={set("contact_name")}
          />
        </Field>
        <Field label="E-mail du contact" htmlFor="c-email">
          <Input
            id="c-email"
            type="email"
            value={form.contact_email}
            onChange={set("contact_email")}
          />
        </Field>
        <Field
          label="Devis à remettre le (heure de Paris)"
          htmlFor="c-deadline"
        >
          <Input
            id="c-deadline"
            type="datetime-local"
            value={form.deadline}
            onChange={set("deadline")}
          />
        </Field>
      </div>
      <div className="flex gap-2">
        <Button type="submit" busy={save.busy}>
          Enregistrer
        </Button>
        <Button type="button" variant="secondary" onClick={() => onDone(null)}>
          Annuler
        </Button>
      </div>
      {save.error && <Alert tone="danger">{save.error}</Alert>}
    </form>
  );
}
