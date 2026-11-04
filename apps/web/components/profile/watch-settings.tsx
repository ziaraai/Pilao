"use client";

import { useState } from "react";

import { Alert, Button, Card, Field, Input, Textarea } from "@/components/ui";
import { api } from "@/lib/api";
import { centsToInput, parseEuros, splitList } from "@/lib/format";
import { useAction } from "@/lib/hooks";
import type { Profile, Trade } from "@/lib/types";

type Form = {
  trades: string[];
  cpv: string;
  include: string;
  exclude: string;
  departments: string;
  min: string;
  max: string;
  y1: string;
  y2: string;
  y3: string;
  minScore: string;
  applyDefaults: boolean;
};

function toForm(p: Profile): Form {
  return {
    trades: p.trades,
    cpv: p.cpv_codes.join(", "),
    include: p.keywords_include.join(", "),
    exclude: p.keywords_exclude.join(", "),
    departments: p.departments.join(", "),
    min: centsToInput(p.min_amount_cents),
    max: centsToInput(p.max_amount_cents),
    y1: centsToInput(p.revenue_y1_cents),
    y2: centsToInput(p.revenue_y2_cents),
    y3: centsToInput(p.revenue_y3_cents),
    minScore: String(p.min_score_alert),
    applyDefaults: false,
  };
}

export function WatchSettings({
  profile,
  trades,
  onSaved,
}: {
  profile: Profile;
  trades: Trade[];
  onSaved: (p: Profile) => void;
}) {
  const [form, setForm] = useState<Form>(() => toForm(profile));
  const [saved, setSaved] = useState(false);
  const [moneyError, setMoneyError] = useState<string | null>(null);
  const save = useAction();
  const set =
    (key: keyof Form) =>
    (e: React.ChangeEvent<HTMLInputElement | HTMLTextAreaElement>) => {
      setSaved(false);
      setMoneyError(null); // the message described the previous value
      setForm((f) => ({ ...f, [key]: e.target.value }));
    };

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const money = {
      min: form.min,
      max: form.max,
      y1: form.y1,
      y2: form.y2,
      y3: form.y3,
    };
    const bad = Object.entries(money).find(
      ([, v]) => v.trim() !== "" && parseEuros(v) === null,
    );
    if (bad) {
      setMoneyError(
        "Montant illisible : écrivez par exemple 125000 ou 125 000,50.",
      );
      return;
    }
    setMoneyError(null);
    const result = await save.run(() =>
      api<Profile>("/profile", {
        method: "PUT",
        json: {
          trades: form.trades,
          cpv_codes: splitList(form.cpv),
          keywords_include: splitList(form.include),
          keywords_exclude: splitList(form.exclude),
          departments: splitList(form.departments),
          min_amount_cents: parseEuros(form.min),
          max_amount_cents: parseEuros(form.max),
          revenue_y1_cents: parseEuros(form.y1),
          revenue_y2_cents: parseEuros(form.y2),
          revenue_y3_cents: parseEuros(form.y3),
          min_score_alert: Number(form.minScore) || 60,
          apply_trade_defaults: form.applyDefaults,
        },
      }),
    );
    if (result) {
      setForm(toForm(result));
      setSaved(true);
      onSaved(result);
    }
  }

  return (
    <Card title="Paramètres de veille" id="veille">
      <form onSubmit={onSubmit} className="space-y-5" noValidate>
        <fieldset>
          <legend className="text-sm font-medium text-slate-800">
            Vos métiers
          </legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2">
            {trades.map((t) => (
              <label
                key={t.code}
                className="flex items-start gap-2 text-sm text-slate-700"
              >
                <input
                  type="checkbox"
                  className="mt-0.5"
                  checked={form.trades.includes(t.code)}
                  onChange={(e) => {
                    setSaved(false);
                    setForm((f) => ({
                      ...f,
                      trades: e.target.checked
                        ? [...f.trades, t.code]
                        : f.trades.filter((x) => x !== t.code),
                    }));
                  }}
                />
                {t.label}
              </label>
            ))}
          </div>
          <label className="mt-3 flex items-center gap-2 text-sm text-slate-700">
            <input
              type="checkbox"
              checked={form.applyDefaults}
              onChange={(e) =>
                setForm((f) => ({ ...f, applyDefaults: e.target.checked }))
              }
            />
            Ajouter les codes CPV et mots-clés habituels de ces métiers
          </label>
        </fieldset>
        <div className="grid gap-4 sm:grid-cols-2">
          <Field
            label="Codes CPV"
            htmlFor="cpv"
            hint="Séparés par des virgules, 8 chiffres (ex. 90911200)."
          >
            <Textarea
              id="cpv"
              rows={2}
              value={form.cpv}
              onChange={set("cpv")}
            />
          </Field>
          <Field
            label="Départements"
            htmlFor="departments"
            hint="Ex. 69, 01, 2A, 974."
          >
            <Textarea
              id="departments"
              rows={2}
              value={form.departments}
              onChange={set("departments")}
            />
          </Field>
          <Field label="Mots-clés recherchés" htmlFor="include">
            <Textarea
              id="include"
              rows={2}
              value={form.include}
              onChange={set("include")}
            />
          </Field>
          <Field
            label="Mots-clés à exclure"
            htmlFor="exclude"
            hint="Ex. désamiantage."
          >
            <Textarea
              id="exclude"
              rows={2}
              value={form.exclude}
              onChange={set("exclude")}
            />
          </Field>
          <Field label="Montant minimum (€ HT)" htmlFor="min">
            <Input
              id="min"
              inputMode="decimal"
              value={form.min}
              onChange={set("min")}
            />
          </Field>
          <Field label="Montant maximum (€ HT)" htmlFor="max">
            <Input
              id="max"
              inputMode="decimal"
              value={form.max}
              onChange={set("max")}
            />
          </Field>
        </div>
        <fieldset>
          <legend className="text-sm font-medium text-slate-800">
            Chiffre d&apos;affaires des 3 derniers exercices (€ HT)
          </legend>
          <div className="mt-2 grid gap-3 sm:grid-cols-3">
            {(["y1", "y2", "y3"] as const).map((k, i) => (
              <Field key={k} label={`Exercice N-${i + 1}`} htmlFor={k}>
                <Input
                  id={k}
                  inputMode="decimal"
                  value={form[k]}
                  onChange={set(k)}
                />
              </Field>
            ))}
          </div>
        </fieldset>
        <Field label="Seuil d'alerte (score sur 100)" htmlFor="minScore">
          <Input
            id="minScore"
            type="number"
            min={0}
            max={100}
            value={form.minScore}
            onChange={set("minScore")}
            className="max-w-32"
          />
        </Field>
        {(moneyError || save.error) && (
          <Alert tone="danger">{moneyError ?? save.error}</Alert>
        )}
        {saved && <Alert tone="ok">Paramètres enregistrés.</Alert>}
        <Button type="submit" busy={save.busy}>
          Enregistrer
        </Button>
      </form>
    </Card>
  );
}
