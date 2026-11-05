"use client";

import { useState } from "react";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { formatDuration, minutesToHours, parseHours } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Bid } from "@/lib/types";

/** P4-02: how long this bid took with Pilao, and how long it usually takes without. */
export function TimeSpent({
  bid,
  onSaved,
}: {
  bid: Bid;
  onSaved: (b: Bid) => void;
}) {
  const [withPilao, setWithPilao] = useState(
    minutesToHours(bid.minutes_with_pilao),
  );
  const [usual, setUsual] = useState(minutesToHours(bid.minutes_usual));
  const [invalid, setInvalid] = useState<string | null>(null);
  const save = useAction();
  if (!["submitted", "won", "lost", "dropped"].includes(bid.status))
    return null;
  const saved =
    bid.minutes_with_pilao != null && bid.minutes_usual != null
      ? bid.minutes_usual - bid.minutes_with_pilao
      : null;

  return (
    <Card title="Temps passé sur ce dossier">
      <form
        className="grid gap-3 sm:grid-cols-[1fr_1fr_auto] sm:items-end"
        onSubmit={async (e) => {
          e.preventDefault();
          const a = parseHours(withPilao);
          const b = parseHours(usual);
          if ((withPilao.trim() && a == null) || (usual.trim() && b == null)) {
            setInvalid("Durée illisible : écrivez par exemple 3, 2,5 ou 2h30.");
            return;
          }
          setInvalid(null);
          const updated = await save.run(() =>
            api<Bid>(`/bids/${bid.id}`, {
              method: "PATCH",
              json: { minutes_with_pilao: a, minutes_usual: b },
            }),
          );
          if (updated) onSaved(updated);
        }}
      >
        <Field
          label="Avec Pilao (heures)"
          htmlFor="minutes-with"
          hint="Relecture et compléments compris."
        >
          <Input
            id="minutes-with"
            inputMode="decimal"
            value={withPilao}
            onChange={(e) => setWithPilao(e.target.value)}
          />
        </Field>
        <Field
          label="Habituellement, sans Pilao (heures)"
          htmlFor="minutes-usual"
          hint="Pour un dossier comparable."
        >
          <Input
            id="minutes-usual"
            inputMode="decimal"
            value={usual}
            onChange={(e) => setUsual(e.target.value)}
          />
        </Field>
        <Button type="submit" variant="secondary" busy={save.busy}>
          Enregistrer
        </Button>
      </form>
      {saved != null && saved > 0 && (
        <p className="mt-3 text-sm text-emerald-800">
          Temps gagné sur ce dossier : <strong>{formatDuration(saved)}</strong>
          {bid.minutes_usual
            ? ` (${Math.round((100 * saved) / bid.minutes_usual)} %)`
            : ""}
          .
        </p>
      )}
      {(invalid || save.error) && (
        <Alert tone="danger">{invalid || save.error}</Alert>
      )}
    </Card>
  );
}
