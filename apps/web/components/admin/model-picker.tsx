"use client";

import { useState } from "react";

import { Loaded } from "@/components/admin/ui";
import { Alert, Button, Input } from "@/components/ui";
import { useAdminAction, useAdminApi } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { eur, matches } from "@/lib/settings";
import type { AdminCatalogueModel } from "@/lib/types";

/** Lot 5: pick a model in OpenRouter's catalogue for one task; it is tried before saving. */
export function ModelPicker({
  task,
  label,
  onSaved,
  onCancel,
}: {
  task: string;
  label: string;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const list = useAdminApi<AdminCatalogueModel[]>(
    `/admin/settings/catalogue?task=${encodeURIComponent(task)}`,
  );
  const [query, setQuery] = useState("");
  const [chosen, setChosen] = useState<string | null>(null);
  const save = useAdminAction();

  return (
    <div className="space-y-3 border-t border-slate-200 bg-slate-50 px-4 py-4">
      <p className="text-sm font-semibold text-brand-navy">
        Choisir le modèle de « {label} »
      </p>
      <Input
        aria-label="Chercher un modèle"
        placeholder="Chercher (claude, mistral…)"
        value={query}
        onChange={(e) => setQuery(e.target.value)}
      />
      <Loaded state={list}>
        {(models) => {
          const shown = models.filter((m) => matches(m, query));
          return shown.length === 0 ? (
            <p className="text-sm text-slate-600">
              Aucun modèle ne correspond.
            </p>
          ) : (
            <ul
              className="max-h-72 divide-y divide-slate-200 overflow-y-auto rounded-md border border-slate-200 bg-white"
              role="listbox"
              aria-label="Modèles du catalogue OpenRouter"
            >
              {shown.map((m) => (
                <li key={m.id}>
                  <button
                    type="button"
                    role="option"
                    aria-selected={chosen === m.id}
                    onClick={() => setChosen(m.id)}
                    className={`flex w-full flex-wrap items-baseline justify-between gap-x-4 gap-y-1 px-3 py-2 text-left text-sm ${chosen === m.id ? "bg-brand-50 ring-2 ring-inset ring-brand-500" : "hover:bg-slate-50"}`}
                  >
                    <span className="min-w-0">
                      <span className="block font-medium text-slate-900">
                        {m.name}
                      </span>
                      <span className="block break-all text-xs text-slate-500">
                        {m.id}
                      </span>
                    </span>
                    <span className="whitespace-nowrap text-xs text-slate-600">
                      {eur(m.price_in_eur)} / {eur(m.price_out_eur)} par million
                      · {Math.round(m.context_length / 1000)} k
                    </span>
                  </button>
                </li>
              ))}
            </ul>
          );
        }}
      </Loaded>
      {save.error && <Alert tone="danger">{save.error}</Alert>}
      <div className="flex flex-wrap gap-2">
        <Button
          busy={save.busy}
          disabled={!chosen}
          onClick={async () => {
            const done = await save.run(() =>
              api(`/admin/settings/models/${encodeURIComponent(task)}`, {
                method: "PUT",
                json: { model_id: chosen },
              }),
            );
            if (done) onSaved();
          }}
        >
          Essayer et enregistrer
        </Button>
        <Button variant="ghost" onClick={onCancel}>
          Annuler
        </Button>
      </div>
      <p className="text-xs text-slate-500">
        Un petit essai réel est fait d&apos;abord (moins d&apos;un centime) : si
        le modèle ne répond pas correctement, rien n&apos;est changé.
      </p>
    </div>
  );
}
