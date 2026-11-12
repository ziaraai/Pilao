"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/admin/dialogs";
import { Alert, Button, Field, Input } from "@/components/ui";
import { useAdminAction } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { creditInput } from "@/lib/credits";
import { MODULE_KEYS, moduleName } from "@/lib/modules";
import type { AdminPlan, AdminPlanIn } from "@/lib/types";

const EMPTY: AdminPlanIn = {
  name: "",
  description: "",
  modules: [...MODULE_KEYS],
  monthly_credits: 0,
  welcome_credits: 0,
  price_note: "",
};

/** Lot 4: create or change a plan. A change to a plan that companies have is confirmed:
 * it applies to them at once. */
export function PlanForm({
  plan,
  onSaved,
  onCancel,
}: {
  plan?: AdminPlan;
  onSaved: () => void;
  onCancel: () => void;
}) {
  const [form, setForm] = useState<AdminPlanIn>(plan ?? EMPTY);
  // the credit fields as typed: an emptied field is not read as 0
  const [typed, setTyped] = useState({
    monthly_credits: String((plan ?? EMPTY).monthly_credits),
    welcome_credits: String((plan ?? EMPTY).welcome_credits),
  });
  const amount = (key: keyof typeof typed) => creditInput(typed[key], 100000);
  const amountsOk =
    amount("monthly_credits") !== null && amount("welcome_credits") !== null;
  const type = (key: keyof typeof typed) => (raw: string) => {
    setTyped((t) => ({ ...t, [key]: raw }));
    const n = creditInput(raw, 100000);
    if (n !== null) setForm((f) => ({ ...f, [key]: n }));
  };
  const [confirming, setConfirming] = useState(false);
  const save = useAdminAction();
  const set =
    <K extends keyof AdminPlanIn>(key: K) =>
    (value: AdminPlanIn[K]) =>
      setForm((f) => ({ ...f, [key]: value }));
  const id = plan?.id ?? "nouvelle";

  async function send() {
    await api(plan ? `/admin/plans/${plan.id}` : "/admin/plans", {
      method: plan ? "PUT" : "POST",
      json: form,
    });
    onSaved();
  }

  return (
    <form
      className="space-y-4 border-t border-slate-200 px-5 py-4"
      noValidate
      onSubmit={async (e) => {
        e.preventDefault();
        if (!amountsOk) return;
        if (plan && plan.organizations > 0) setConfirming(true);
        else await save.run(send);
      }}
    >
      <div className="grid gap-4 sm:grid-cols-2">
        <Field label="Nom" htmlFor={`plan-name-${id}`}>
          <Input
            id={`plan-name-${id}`}
            maxLength={80}
            value={form.name}
            onChange={(e) => set("name")(e.target.value)}
          />
        </Field>
        <Field
          label="Votre prix (jamais montré au client)"
          htmlFor={`plan-price-${id}`}
          hint="Ex. : 49 € HT par mois."
        >
          <Input
            id={`plan-price-${id}`}
            maxLength={120}
            value={form.price_note}
            onChange={(e) => set("price_note")(e.target.value)}
          />
        </Field>
      </div>
      <Field
        label="Phrase vue par le client"
        htmlFor={`plan-description-${id}`}
      >
        <Input
          id={`plan-description-${id}`}
          maxLength={200}
          value={form.description}
          onChange={(e) => set("description")(e.target.value)}
        />
      </Field>
      <fieldset>
        <legend className="text-sm font-medium text-slate-800">
          Modules compris
        </legend>
        <div className="mt-2 flex flex-wrap gap-4">
          {MODULE_KEYS.map((key) => (
            <label key={key} className="flex items-center gap-2 text-sm">
              <input
                type="checkbox"
                checked={form.modules.includes(key)}
                onChange={(e) =>
                  set("modules")(
                    e.target.checked
                      ? MODULE_KEYS.filter(
                          (k) => k === key || form.modules.includes(k),
                        )
                      : form.modules.filter((k) => k !== key),
                  )
                }
              />
              {moduleName(key)}
            </label>
          ))}
        </div>
      </fieldset>
      <div className="grid gap-4 sm:grid-cols-2">
        <Field
          label="Crédits par mois"
          htmlFor={`plan-monthly-${id}`}
          hint="Remis à ce niveau le 1er de chaque mois."
        >
          <Input
            id={`plan-monthly-${id}`}
            type="number"
            min={0}
            max={100000}
            value={typed.monthly_credits}
            onChange={(e) => type("monthly_credits")(e.target.value)}
          />
        </Field>
        <Field
          label="Crédits offerts à l'arrivée"
          htmlFor={`plan-welcome-${id}`}
          hint="Donnés une seule fois, n'expirent pas."
        >
          <Input
            id={`plan-welcome-${id}`}
            type="number"
            min={0}
            max={100000}
            value={typed.welcome_credits}
            onChange={(e) => type("welcome_credits")(e.target.value)}
          />
        </Field>
      </div>
      {save.error && <Alert tone="danger">{save.error}</Alert>}
      <div className="flex gap-2">
        <Button
          type="submit"
          busy={save.busy}
          disabled={!form.name.trim() || !amountsOk}
        >
          Enregistrer
        </Button>
        <Button type="button" variant="ghost" onClick={onCancel}>
          Annuler
        </Button>
      </div>
      {confirming && plan && (
        <ConfirmDialog
          title={`Modifier « ${plan.name} » ?`}
          confirmLabel="Enregistrer"
          onConfirm={send}
          onClose={() => setConfirming(false)}
        >
          <p>
            Ces changements s&apos;appliquent aux {plan.organizations}{" "}
            entreprise{plan.organizations > 1 ? "s" : ""} qui ont cette formule.
          </p>
        </ConfirmDialog>
      )}
    </form>
  );
}
