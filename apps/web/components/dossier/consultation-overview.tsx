"use client";

import { useRef, useState } from "react";

import { PaidButton } from "@/components/paid-button";
import { Alert, Button, Card, Field, Input, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import {
  type FactColumn,
  consultationCard,
  missingFacts,
  readingText,
} from "@/lib/consultation";
import { formatDateTime, fromParisInput, toParisInput } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Bid, ConsultationRead } from "@/lib/types";

/** Empty fields stand out in yellow: what the documents did not say, to fill by hand. */
const TO_FILL = "bg-yellow-50 ring-1 ring-inset ring-yellow-300";

/**
 * Who asks for the quote, where the works are and how to reach the client (ADR-052), at the
 * top of a consultation. Pilao reads them in the documents received (25/11): each fact shows
 * the file and page it was read on; what the documents do not say stays empty, in yellow.
 */
export function ConsultationOverview({
  bid,
  onSaved,
  onRead,
}: {
  bid: Bid;
  onSaved: (b: Bid) => void;
  /** The reading just ended: the dossier (its card, its price files) is read again. */
  onRead: () => void;
}) {
  const [editing, setEditing] = useState(false);
  const wasReading = useRef(false);
  const read = useApi<ConsultationRead>(
    `/bids/${bid.id}/consultation-read`,
    (r) => {
      const busy = r.status === "reading";
      if (wasReading.current && !busy) onRead();
      wasReading.current = busy;
      return busy;
    },
  );
  const relaunch = useAction();
  const rows = consultationCard(bid);
  const missing = missingFacts(rows);
  const state = read.data;

  async function readAgain() {
    const next = await relaunch.run(() =>
      api<ConsultationRead>(`/bids/${bid.id}/consultation-read`, {
        method: "POST",
      }),
    );
    if (next) read.reload(); // follow the reading
  }

  return (
    <Card
      title="La consultation"
      color="blue"
      icon="bids"
      actions={
        !editing && (
          <Button variant="secondary" onClick={() => setEditing(true)}>
            {missing > 0 ? "Compléter" : "Modifier"}
          </Button>
        )
      }
    >
      <div className="space-y-4">
        {state && (
          <ReadingState
            read={state}
            dceReady={!!bid.progress?.dce_ready}
            busy={relaunch.busy}
            onRead={readAgain}
          />
        )}
        {relaunch.error && <Alert tone="danger">{relaunch.error}</Alert>}
        {editing ? (
          <ConsultationForm
            bid={bid}
            onDone={(b) => {
              setEditing(false);
              if (b) onSaved(b);
            }}
          />
        ) : (
          <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-[auto_1fr]">
            {rows.map((r) => (
              <div key={r.column} className="contents">
                <dt className="text-slate-600">{r.label}</dt>
                <dd>
                  {r.missing ? (
                    <span
                      className={`inline-flex rounded px-2 py-0.5 text-amber-900 ${TO_FILL}`}
                    >
                      {r.value ? `${r.value} — à préciser` : "À compléter"}
                    </span>
                  ) : r.column === "contact_email" ? (
                    <a
                      className="text-brand-navy underline"
                      href={`mailto:${r.value}`}
                    >
                      {r.value}
                    </a>
                  ) : (
                    <span className="whitespace-pre-line">{r.value}</span>
                  )}
                  {r.source && !r.missing && (
                    <span className="ml-2 text-xs text-slate-500">
                      ({r.source})
                    </span>
                  )}
                </dd>
              </div>
            ))}
            <dt className="text-slate-600">Lot</dt>
            <dd>{bid.lot_label ?? "—"}</dd>
            <dt className="text-slate-600">Devis à remettre le</dt>
            <dd>{formatDateTime(bid.deadline_at)}</dd>
          </dl>
        )}
      </div>
    </Card>
  );
}

function ReadingState({
  read,
  dceReady,
  busy,
  onRead,
}: {
  read: ConsultationRead;
  dceReady: boolean;
  busy: boolean;
  onRead: () => Promise<void>;
}) {
  if (read.status === "reading")
    return (
      <p role="status" className="text-sm text-slate-700">
        {readingText(read)}
      </p>
    );
  if (read.status === "none")
    return dceReady ? (
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-slate-700">
          Pilao peut lire les documents reçus pour remplir cette fiche et
          trouver le fichier de prix.
        </p>
        <PaidButton
          action="price_read"
          label="Lire les documents"
          busy={busy}
          onClick={onRead}
        />
      </div>
    ) : (
      <p className="text-sm text-slate-600">
        Déposez les documents reçus du client : Pilao remplit cette fiche et
        trouve le fichier de prix.
      </p>
    );
  if (read.status === "ready")
    return (
      <div className="flex flex-wrap items-center gap-3">
        <p className="text-sm text-slate-700">{readingText(read)}</p>
        <PaidButton
          action="price_read"
          label="Relire les documents"
          variant="secondary"
          busy={busy}
          onClick={onRead}
        />
      </div>
    );
  return (
    <div className="space-y-2">
      <Alert tone="warning">{readingText(read)}</Alert>
      <PaidButton
        action="price_read"
        label="Relancer la lecture"
        busy={busy}
        onClick={onRead}
      />
    </div>
  );
}

type FormState = Record<FactColumn | "lot_label" | "deadline", string>;

function ConsultationForm({
  bid,
  onDone,
}: {
  bid: Bid;
  onDone: (b: Bid | null) => void;
}) {
  const rows = consultationCard(bid);
  const [form, setForm] = useState<FormState>(() => ({
    ...(Object.fromEntries(
      // the title Pilao gave until the documents are read is offered empty
      rows.map((r) => [r.column, r.missing ? "" : r.value]),
    ) as Record<FactColumn, string>),
    lot_label: bid.lot_label ?? "",
    deadline: toParisInput(bid.deadline_at),
  }));
  const save = useAction();
  const set =
    (k: keyof FormState) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) =>
      setForm({ ...form, [k]: e.target.value });

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const facts = Object.fromEntries(
      rows
        .filter((r) => r.column !== "title")
        .map((r) => [r.column, form[r.column].trim() || null]),
    );
    const next = await save.run(() =>
      api<Bid>(`/bids/${bid.id}`, {
        method: "PATCH",
        json: {
          ...facts,
          // an emptied title keeps the one there (a dossier always has one)
          ...(form.title.trim() ? { title: form.title.trim() } : {}),
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
        {rows.map((r) => {
          const id = `c-${r.column}`;
          const empty = !form[r.column].trim();
          const className = empty ? TO_FILL : undefined;
          return (
            <Field
              key={r.column}
              label={r.source ? `${r.label} (${r.source})` : r.label}
              htmlFor={id}
            >
              {r.long ? (
                <Textarea
                  id={id}
                  rows={2}
                  maxLength={5000}
                  value={form[r.column]}
                  className={className}
                  onChange={set(r.column)}
                />
              ) : (
                <Input
                  id={id}
                  type={r.column === "contact_email" ? "email" : "text"}
                  maxLength={300}
                  value={form[r.column]}
                  className={className}
                  onChange={set(r.column)}
                />
              )}
            </Field>
          );
        })}
        <Field label="Lot" htmlFor="c-lot">
          <Input
            id="c-lot"
            value={form.lot_label}
            placeholder="ex. Lot 16"
            onChange={set("lot_label")}
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
      <p className="text-xs text-slate-500">
        Les cases jaunes sont celles que les documents ne disent pas. Ce que
        vous saisissez n&apos;est jamais remplacé par une nouvelle lecture.
      </p>
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
