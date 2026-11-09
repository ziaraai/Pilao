"use client";

import { useState } from "react";

import { Alert, Button, Card, Field, Input, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { centsToInput, parseEuros } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Bid } from "@/lib/types";

/** US-5.4: once submitted, what the company proposed and what the buyer decided. */
export function ResultSection({
  bid,
  onSaved,
}: {
  bid: Bid;
  onSaved: (b: Bid) => void;
}) {
  const [amount, setAmount] = useState(
    centsToInput(bid.submitted_amount_cents),
  );
  const [rank, setRank] = useState(
    bid.result_rank ? String(bid.result_rank) : "",
  );
  const [notes, setNotes] = useState(bid.result_notes ?? "");
  const [saved, setSaved] = useState(false);
  const [invalid, setInvalid] = useState<string | null>(null);
  const save = useAction();
  if (!["submitted", "won", "lost"].includes(bid.status)) return null;
  return (
    <Card title="Résultat" color="violet" icon="results">
      <form
        className="grid gap-3 sm:grid-cols-[1fr_1fr_2fr]"
        onSubmit={async (e) => {
          e.preventDefault();
          const cents = amount.trim() ? parseEuros(amount) : null;
          if (amount.trim() && cents == null) {
            setInvalid(
              "Montant illisible : écrivez par exemple 98 000 ou 98000,50.",
            );
            return;
          }
          setInvalid(null);
          const updated = await save.run(() =>
            api<Bid>(`/bids/${bid.id}`, {
              method: "PATCH",
              json: {
                submitted_amount_cents: cents,
                result_rank: rank ? Number(rank) : null,
                result_notes: notes.trim() || null,
              },
            }),
          );
          if (updated) {
            setSaved(true);
            onSaved(updated);
          }
        }}
      >
        <Field
          label="Montant proposé (€ HT)"
          htmlFor="result-amount"
          error={invalid ?? undefined}
        >
          <Input
            id="result-amount"
            inputMode="decimal"
            value={amount}
            onChange={(e) => {
              setSaved(false);
              setAmount(e.target.value);
            }}
          />
        </Field>
        <Field label="Classement" htmlFor="result-rank" hint="1 = retenu">
          <Input
            id="result-rank"
            type="number"
            min={1}
            value={rank}
            onChange={(e) => {
              setSaved(false);
              setRank(e.target.value);
            }}
          />
        </Field>
        <Field
          label="Notes obtenues, retours de l'acheteur"
          htmlFor="result-notes"
        >
          <Textarea
            id="result-notes"
            rows={2}
            value={notes}
            maxLength={5000}
            placeholder="Ex. : technique 52/60, prix 35/40"
            onChange={(e) => {
              setSaved(false);
              setNotes(e.target.value);
            }}
          />
        </Field>
        <div className="flex items-center gap-3 sm:col-span-3">
          <Button type="submit" busy={save.busy}>
            Enregistrer le résultat
          </Button>
          {saved && (
            <span role="status" className="text-sm text-emerald-700">
              Enregistré.
            </span>
          )}
        </div>
        {save.error && (
          <div className="sm:col-span-3">
            <Alert tone="danger">{save.error}</Alert>
          </div>
        )}
      </form>
    </Card>
  );
}
