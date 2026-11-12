"use client";

import { useState } from "react";

import { ConfirmDialog } from "@/components/admin/dialogs";
import { Loaded } from "@/components/admin/ui";
import {
  Alert,
  Button,
  Card,
  Field,
  Input,
  Select,
  tableHead,
  tableRow,
} from "@/components/ui";
import { useAdminAction, useAdminApi } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { credits } from "@/lib/credits";
import { formatDate, formatDateTimeShort } from "@/lib/format";
import type { AdminOrgCredits, AdminPlan, CreditLine } from "@/lib/types";

function what(line: CreditLine): string {
  if (line.kind === "welcome") return "Crédits offerts";
  if (line.kind === "grant") return "Crédits ajoutés par Pilao";
  if (line.kind === "refund") return line.reason ?? "Remboursé";
  return line.action_name ?? "Action";
}

/** Lot 4 (US-6.13): the company's plan, its credits, a top-up, the history. */
export function OrgPlan({
  orgId,
  orgName,
  onChanged,
}: {
  orgId: string;
  orgName: string;
  onChanged: () => void;
}) {
  const base = `/admin/organizations/${orgId}/credits`;
  const state = useAdminApi<AdminOrgCredits>(base);
  const plans = useAdminApi<AdminPlan[]>("/admin/plans");
  const [chosen, setChosen] = useState("");
  const [confirming, setConfirming] = useState(false);
  const [amount, setAmount] = useState("");
  const [reason, setReason] = useState("");
  const [done, setDone] = useState<string | null>(null);
  const act = useAdminAction();

  return (
    <Loaded state={state}>
      {(c) => {
        const choices = (plans.data ?? []).filter(
          (p) => !p.archived && p.id !== c.plan.id,
        );
        const target = choices.find((p) => p.id === chosen);
        return (
          <Card title="Formule et crédits" color="violet" flush>
            <div className="grid gap-6 px-5 py-4 lg:grid-cols-2">
              <div className="space-y-3">
                <p className="text-sm text-slate-600">Formule</p>
                <p className="text-lg font-bold text-brand-navy">
                  {c.plan.name}
                </p>
                <div className="flex flex-wrap items-end gap-2">
                  <Field label="Changer de formule" htmlFor={`plan-${orgId}`}>
                    <Select
                      id={`plan-${orgId}`}
                      value={chosen}
                      onChange={(e) => setChosen(e.target.value)}
                    >
                      <option value="">Choisir…</option>
                      {choices.map((p) => (
                        <option key={p.id} value={p.id}>
                          {p.name}
                        </option>
                      ))}
                    </Select>
                  </Field>
                  <Button
                    variant="secondary"
                    disabled={!target}
                    onClick={() => setConfirming(true)}
                    className="mb-6"
                  >
                    Changer
                  </Button>
                </div>
              </div>
              <div className="space-y-1 text-sm text-slate-700">
                <p className="text-3xl font-bold text-violet-800">
                  {credits(c.total)}
                </p>
                {c.monthly_allowance > 0 && (
                  <p>
                    Crédits du mois : {c.monthly_left} sur {c.monthly_allowance}{" "}
                    (renouvelés le {formatDate(c.renews_on)})
                  </p>
                )}
                <p>Crédits supplémentaires : {c.extra}</p>
                <form
                  className="flex flex-wrap items-end gap-2 pt-3"
                  noValidate
                  onSubmit={async (e) => {
                    e.preventDefault();
                    setDone(null);
                    const res = await act.run(() =>
                      api(base, {
                        json: { amount: Number(amount), reason },
                      }),
                    );
                    if (res) {
                      setDone(`${credits(Number(amount))} ajoutés.`);
                      setAmount("");
                      setReason("");
                      state.reload();
                    }
                  }}
                >
                  <Field
                    label="Ajouter des crédits"
                    htmlFor={`amount-${orgId}`}
                  >
                    <Input
                      id={`amount-${orgId}`}
                      type="number"
                      min={1}
                      max={100000}
                      className="w-24"
                      value={amount}
                      onChange={(e) => setAmount(e.target.value)}
                    />
                  </Field>
                  <Field label="Raison de l'ajout" htmlFor={`reason-${orgId}`}>
                    <Input
                      id={`reason-${orgId}`}
                      maxLength={200}
                      value={reason}
                      onChange={(e) => setReason(e.target.value)}
                    />
                  </Field>
                  <Button
                    type="submit"
                    busy={act.busy}
                    disabled={!Number(amount) || !reason.trim()}
                    className="mb-6"
                  >
                    Ajouter
                  </Button>
                </form>
              </div>
            </div>
            {(done || act.error) && (
              <div className="px-5 pb-4">
                {act.error ? (
                  <Alert tone="danger">{act.error}</Alert>
                ) : (
                  <Alert tone="ok">{done}</Alert>
                )}
              </div>
            )}
            {c.history.length > 0 && (
              <div className="overflow-x-auto border-t border-slate-200">
                <table className="w-full text-sm">
                  <thead>
                    <tr className={tableHead}>
                      <th className="px-4 py-2 text-left">Date</th>
                      <th className="px-4 py-2 text-left">Mouvement</th>
                      <th className="px-4 py-2 text-left">Dossier</th>
                      <th className="px-4 py-2 text-left">Par</th>
                      <th className="px-4 py-2 text-right">Crédits</th>
                    </tr>
                  </thead>
                  <tbody>
                    {c.history.map((h, i) => (
                      <tr key={`${h.at}-${i}`} className={tableRow}>
                        <td className="whitespace-nowrap px-4 py-2">
                          {formatDateTimeShort(h.at)}
                        </td>
                        <td className="px-4 py-2">
                          {what(h)}
                          {h.kind === "grant" && h.reason && (
                            <span className="block text-xs text-slate-500">
                              {h.reason}
                            </span>
                          )}
                        </td>
                        <td className="px-4 py-2">{h.bid_title ?? "—"}</td>
                        <td className="px-4 py-2">{h.user_name ?? "—"}</td>
                        <td
                          className={`whitespace-nowrap px-4 py-2 text-right font-semibold ${h.credits < 0 ? "text-red-700" : "text-emerald-700"}`}
                        >
                          {h.credits > 0 ? `+${h.credits}` : h.credits}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {confirming && target && (
              <ConfirmDialog
                title={`Passer ${orgName} en « ${target.name} » ?`}
                confirmLabel="Changer de formule"
                onConfirm={async () => {
                  await api(`/admin/organizations/${orgId}/plan`, {
                    method: "PUT",
                    json: { plan_id: target.id },
                  });
                  setChosen("");
                  state.reload();
                  onChanged();
                }}
                onClose={() => setConfirming(false)}
              >
                <p>
                  Ses modules deviennent ceux de la formule (les exceptions
                  tombent) et ses crédits du mois aussi. Ses crédits
                  supplémentaires sont gardés.
                </p>
              </ConfirmDialog>
            )}
          </Card>
        );
      }}
    </Loaded>
  );
}
