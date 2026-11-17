"use client";

import { useState } from "react";

import { Alert, Button, Card, Input, Select } from "@/components/ui";
import { api } from "@/lib/api";
import {
  PRICE_UNITS,
  type ServiceRow,
  serviceErrors,
  servicesFromRows,
} from "@/lib/consultation";
import { centsToInput } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Service } from "@/lib/types";

const EMPTY: ServiceRow = { name: "", unit: "m²", price: "", description: "" };

const rowsOf = (services: Service[]): ServiceRow[] =>
  services.map((s) => ({
    name: s.name,
    unit: s.unit,
    price: centsToInput(s.price_cents),
    description: s.description ?? "",
  }));

/**
 * « Ma liste de prix » (ADR-052): the company's services with their unit and price, typed
 * once. When a price file is read, the lines doing the same work, in the same unit, get
 * this price (always to check, never forced).
 */
export function PriceListCard() {
  const services = useApi<Service[]>("/profile/services");
  if (services.error) return <Alert tone="danger">{services.error}</Alert>;
  if (!services.data) return null;
  return (
    <Card title="Ma liste de prix" color="brand" icon="profile">
      <PriceListForm
        key={services.data.map((s) => s.id).join()}
        services={services.data}
        onSaved={services.setData}
      />
    </Card>
  );
}

function PriceListForm({
  services,
  onSaved,
}: {
  services: Service[];
  onSaved: (s: Service[]) => void;
}) {
  const [rows, setRows] = useState<ServiceRow[]>(
    services.length ? rowsOf(services) : [EMPTY],
  );
  const [errors, setErrors] = useState<Record<number, string>>({});
  const [saved, setSaved] = useState(false);
  const save = useAction();

  const set = (i: number, patch: Partial<ServiceRow>) => {
    setSaved(false);
    setRows(rows.map((r, j) => (j === i ? { ...r, ...patch } : r)));
  };

  async function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    const found = serviceErrors(rows);
    setErrors(found);
    if (Object.keys(found).length) return;
    const next = await save.run(() =>
      api<Service[]>("/profile/services", {
        method: "PUT",
        json: { services: servicesFromRows(rows) },
      }),
    );
    if (next) {
      setSaved(true);
      onSaved(next);
    }
  }

  return (
    <form onSubmit={onSubmit} noValidate className="space-y-3">
      <p className="text-sm text-slate-700">
        Vos prestations et leur prix HT. À la lecture d&apos;un fichier de prix
        (DPGF, BPU, DQE), Pilao met ce prix sur les lignes qui font le même
        travail, dans la même unité ; vous le vérifiez avant d&apos;envoyer.
      </p>
      <ul className="space-y-3">
        {rows.map((r, i) => (
          <li
            key={i}
            className="grid gap-2 rounded-md border border-slate-200 p-3 sm:grid-cols-[2fr_6rem_7rem_auto]"
          >
            <Input
              aria-label={`Prestation ${i + 1}`}
              placeholder="ex. Nettoyage de fin de chantier avant OPR"
              value={r.name}
              onChange={(e) => set(i, { name: e.target.value })}
            />
            <Select
              aria-label={`Unité de la prestation ${i + 1}`}
              value={r.unit}
              onChange={(e) => set(i, { unit: e.target.value })}
            >
              {PRICE_UNITS.map((u) => (
                <option key={u} value={u}>
                  {u}
                </option>
              ))}
            </Select>
            <Input
              aria-label={`Prix HT de la prestation ${i + 1}`}
              inputMode="decimal"
              placeholder="€ HT"
              className="text-right"
              value={r.price}
              onChange={(e) => set(i, { price: e.target.value })}
            />
            <Button
              type="button"
              variant="secondary"
              aria-label={`Retirer la prestation ${i + 1}`}
              onClick={() => {
                setSaved(false);
                setErrors({});
                setRows(rows.filter((_, j) => j !== i));
              }}
            >
              Retirer
            </Button>
            <Input
              aria-label={`Description de la prestation ${i + 1}`}
              placeholder="Description reprise dans le devis (facultatif)"
              className="sm:col-span-4"
              value={r.description}
              onChange={(e) => set(i, { description: e.target.value })}
            />
            {errors[i] && (
              <p className="text-xs text-red-700 sm:col-span-4">{errors[i]}</p>
            )}
          </li>
        ))}
      </ul>
      <div className="flex flex-wrap items-center gap-3">
        <Button
          type="button"
          variant="secondary"
          onClick={() => setRows([...rows, EMPTY])}
          disabled={rows.length >= 100}
        >
          Ajouter une prestation
        </Button>
        <Button type="submit" busy={save.busy}>
          Enregistrer la liste
        </Button>
        {saved && (
          <span role="status" className="text-sm text-emerald-700">
            Liste enregistrée.
          </span>
        )}
      </div>
      {save.error && <Alert tone="danger">{save.error}</Alert>}
    </form>
  );
}
