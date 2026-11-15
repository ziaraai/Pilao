"use client";

import { useState } from "react";

import { Alert, Button, Card, Field, Input } from "@/components/ui";
import { api } from "@/lib/api";
import { centsToInput, parseEuros } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Rates } from "@/lib/types";

type Pct = "night_pct" | "sunday_pct" | "holiday_pct";
const PCTS: { key: Pct; label: string }[] = [
  { key: "night_pct", label: "Majoration de nuit (%)" },
  { key: "sunday_pct", label: "Majoration du dimanche (%)" },
  { key: "holiday_pct", label: "Majoration des jours fériés (%)" },
];

/** « 25 » → 25; empty → null; anything else → undefined (refused). */
function pctInput(text: string): number | null | undefined {
  const t = text.trim().replace("%", "").trim();
  if (t === "") return null;
  return /^\d{1,3}$/.test(t) && Number(t) <= 300 ? Number(t) : undefined;
}

/**
 * Chiffrage (ADR-049): the company's hourly rate and surcharges, typed once. Pilao prices
 * the lines of a price file with them: hours × rate, and the rate plus its surcharge for
 * an hourly price at night, on Sunday or on a public holiday.
 */
export function RatesCard({ onSaved }: { onSaved?: (r: Rates) => void }) {
  const rates = useApi<Rates>("/profile/rates");
  if (rates.error) return <Alert tone="danger">{rates.error}</Alert>;
  if (!rates.data) return null;
  return (
    <Card title="Taux horaires pour le chiffrage" color="brand" icon="profile">
      <RatesForm
        rates={rates.data}
        onSaved={(r) => {
          rates.setData(r);
          onSaved?.(r);
        }}
      />
    </Card>
  );
}

export function RatesForm({
  rates,
  onSaved,
}: {
  rates: Rates;
  onSaved: (r: Rates) => void;
}) {
  const [hourly, setHourly] = useState(centsToInput(rates.hourly_rate_cents));
  const [pcts, setPcts] = useState<Record<Pct, string>>({
    night_pct: rates.night_pct?.toString() ?? "",
    sunday_pct: rates.sunday_pct?.toString() ?? "",
    holiday_pct: rates.holiday_pct?.toString() ?? "",
  });
  const [saved, setSaved] = useState(false);
  const [invalid, setInvalid] = useState<string | null>(null);
  const save = useAction();

  return (
    <form
      className="space-y-4"
      onSubmit={async (e) => {
        e.preventDefault();
        setSaved(false);
        const rate = hourly.trim() === "" ? null : parseEuros(hourly);
        if (rate === null && hourly.trim() !== "") {
          setInvalid("Taux horaire invalide (ex. : 24,50).");
          return;
        }
        const values = Object.fromEntries(
          PCTS.map((p) => [p.key, pctInput(pcts[p.key])]),
        ) as Record<Pct, number | null | undefined>;
        if (Object.values(values).some((v) => v === undefined)) {
          setInvalid("Majoration invalide : un nombre entier de 0 à 300.");
          return;
        }
        setInvalid(null);
        const next = await save.run(() =>
          api<Rates>("/profile/rates", {
            method: "PUT",
            json: { hourly_rate_cents: rate, ...values },
          }),
        );
        if (next) {
          setSaved(true);
          onSaved(next);
        }
      }}
    >
      <p className="text-sm text-slate-600">
        Pilao calcule vos prix avec ces taux : heures × taux horaire, et le taux
        majoré pour les heures de nuit, du dimanche et des jours fériés. Un taux
        laissé vide laisse les prix concernés à compléter : Pilao ne devine
        jamais un prix.
      </p>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Taux horaire de vente (€ HT)" htmlFor="rate-hourly">
          <Input
            id="rate-hourly"
            inputMode="decimal"
            placeholder="Ex. : 24,50"
            value={hourly}
            onChange={(e) => setHourly(e.target.value)}
          />
        </Field>
        {PCTS.map((p) => (
          <Field key={p.key} label={p.label} htmlFor={`rate-${p.key}`}>
            <Input
              id={`rate-${p.key}`}
              inputMode="numeric"
              placeholder="Ex. : 25"
              value={pcts[p.key]}
              onChange={(e) =>
                setPcts((old) => ({ ...old, [p.key]: e.target.value }))
              }
            />
          </Field>
        ))}
      </div>
      {(invalid || save.error) && (
        <Alert tone="danger">{invalid ?? save.error}</Alert>
      )}
      <div className="flex items-center gap-3">
        <Button type="submit" busy={save.busy}>
          Enregistrer les taux
        </Button>
        {saved && (
          <span role="status" className="text-sm text-emerald-800">
            Taux enregistrés
          </span>
        )}
      </div>
    </form>
  );
}
