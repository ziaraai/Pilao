"use client";

import { useState } from "react";

import { PlanForm } from "@/components/admin/plan-form";
import {
  AdminTitle,
  CELL,
  HEAD,
  Loaded,
  NUM,
  Pill,
} from "@/components/admin/ui";
import {
  Alert,
  Button,
  Card,
  Input,
  tableHead,
  tableRow,
} from "@/components/ui";
import { moduleShort } from "@/lib/admin";
import { useAdminAction, useAdminApi } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { creditInput } from "@/lib/credits";
import { formatEuros } from "@/lib/format";
import { moduleName } from "@/lib/modules";
import type { AdminCreditPrice, AdminPlan } from "@/lib/types";

/** Lot 4 (US-6.11, US-6.12): the plans, and the price in credits of each paid action. */
export default function AdminPlansPage() {
  const plans = useAdminApi<AdminPlan[]>("/admin/plans");
  const prices = useAdminApi<AdminCreditPrice[]>("/admin/credit-prices");
  const [editing, setEditing] = useState<string | null>(null);
  const act = useAdminAction();

  async function run(fn: () => Promise<unknown>) {
    if (await act.run(async () => (await fn(), true))) plans.reload();
  }

  return (
    <div className="space-y-6">
      <AdminTitle
        title="Formules"
        readOnly={false}
        subtitle="Une formule donne des modules et des crédits. Le client ne voit jamais d'euros : seulement ses crédits."
      />
      <Loaded state={plans}>
        {(list) => (
          <Card
            title="Formules"
            color="brand"
            flush
            actions={
              <Button
                variant="secondary"
                onClick={() => setEditing(editing === "new" ? null : "new")}
                aria-expanded={editing === "new"}
              >
                Nouvelle formule
              </Button>
            }
          >
            {act.error && (
              <div className="px-5 pt-4">
                <Alert tone="danger">{act.error}</Alert>
              </div>
            )}
            {editing === "new" && (
              <PlanForm
                onSaved={() => {
                  setEditing(null);
                  plans.reload();
                }}
                onCancel={() => setEditing(null)}
              />
            )}
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className={tableHead}>
                    <th className={HEAD}>Formule</th>
                    <th className={HEAD}>Modules</th>
                    <th className={NUM}>Crédits par mois</th>
                    <th className={NUM}>Offerts</th>
                    <th className={HEAD}>Votre prix</th>
                    <th className={NUM}>Entreprises</th>
                    <th className={HEAD}>Actions</th>
                  </tr>
                </thead>
                <tbody>
                  {list.map((p) => (
                    <tr key={p.id} className={tableRow}>
                      <td className={CELL}>
                        <span className="font-semibold text-brand-navy">
                          {p.name}
                        </span>
                        <span className="ml-2 inline-flex gap-1 align-middle">
                          {p.is_default && <Pill tone="ok">Par défaut</Pill>}
                          {p.archived && <Pill tone="neutral">Archivée</Pill>}
                        </span>
                        {p.description && (
                          <span className="block text-xs text-slate-500">
                            {p.description}
                          </span>
                        )}
                      </td>
                      <td className={CELL}>
                        {p.modules.length
                          ? p.modules.map(moduleShort).join(", ")
                          : "Aucun"}
                      </td>
                      <td className={NUM}>{p.monthly_credits}</td>
                      <td className={NUM}>{p.welcome_credits}</td>
                      <td className={CELL}>{p.price_note || "—"}</td>
                      <td className={NUM}>{p.organizations}</td>
                      <td className={CELL}>
                        <span className="flex flex-wrap gap-1">
                          <Button
                            variant="secondary"
                            className="px-2 py-1 text-xs"
                            aria-label={`Modifier ${p.name}`}
                            onClick={() =>
                              setEditing(editing === p.id ? null : p.id)
                            }
                          >
                            Modifier
                          </Button>
                          {!p.is_default && !p.archived && (
                            <Button
                              variant="secondary"
                              className="px-2 py-1 text-xs"
                              aria-label={`Mettre ${p.name} par défaut`}
                              onClick={() =>
                                run(() =>
                                  api(`/admin/plans/${p.id}/default`, {
                                    method: "PUT",
                                  }),
                                )
                              }
                            >
                              Par défaut
                            </Button>
                          )}
                          {!p.is_default && (
                            <Button
                              variant="ghost"
                              className="px-2 py-1 text-xs"
                              aria-label={`${p.archived ? "Désarchiver" : "Archiver"} ${p.name}`}
                              onClick={() =>
                                run(() =>
                                  api(
                                    `/admin/plans/${p.id}/${p.archived ? "unarchive" : "archive"}`,
                                    { method: "POST" },
                                  ),
                                )
                              }
                            >
                              {p.archived ? "Désarchiver" : "Archiver"}
                            </Button>
                          )}
                        </span>
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
            {editing && editing !== "new" && (
              <PlanForm
                key={editing}
                plan={list.find((p) => p.id === editing)}
                onSaved={() => {
                  setEditing(null);
                  plans.reload();
                }}
                onCancel={() => setEditing(null)}
              />
            )}
          </Card>
        )}
      </Loaded>
      <Loaded state={prices}>
        {(list) => <PriceTable rows={list} onSaved={prices.reload} />}
      </Loaded>
    </div>
  );
}

function PriceTable({
  rows,
  onSaved,
}: {
  rows: AdminCreditPrice[];
  onSaved: () => void;
}) {
  const [values, setValues] = useState<Record<string, string>>(() =>
    Object.fromEntries(rows.map((r) => [r.action, String(r.credits)])),
  );
  const save = useAdminAction();
  return (
    <Card title="Prix des actions" color="violet" flush>
      {save.error && (
        <div className="px-5 pt-4">
          <Alert tone="danger">{save.error}</Alert>
        </div>
      )}
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className={tableHead}>
              <th className={HEAD}>Action</th>
              <th className={HEAD}>Module</th>
              <th className={HEAD}>Prix en crédits</th>
              <th className={NUM}>Utilisations (30 j)</th>
              <th className={NUM}>Coût réel moyen (30 j)</th>
            </tr>
          </thead>
          <tbody>
            {rows.map((r) => (
              <tr key={r.action} className={tableRow}>
                <td className={CELL}>{r.name}</td>
                <td className={CELL}>{moduleName(r.module)}</td>
                <td className={CELL}>
                  <span className="flex items-center gap-2">
                    <Input
                      aria-label={`Prix de « ${r.name} »`}
                      type="number"
                      min={0}
                      max={1000}
                      className="w-20"
                      value={values[r.action] ?? ""}
                      onChange={(e) =>
                        setValues((v) => ({ ...v, [r.action]: e.target.value }))
                      }
                    />
                    {values[r.action] !== String(r.credits) && (
                      <Button
                        className="px-2 py-1 text-xs"
                        busy={save.busy}
                        disabled={
                          creditInput(values[r.action] ?? "", 1000) === null
                        }
                        onClick={async () => {
                          const credits = creditInput(
                            values[r.action] ?? "",
                            1000,
                          );
                          if (credits === null) return; // empty: never saved as « free »
                          const done = await save.run(() =>
                            api(`/admin/credit-prices/${r.action}`, {
                              method: "PUT",
                              json: { credits },
                            }),
                          );
                          if (done) onSaved();
                        }}
                      >
                        Enregistrer
                      </Button>
                    )}
                  </span>
                </td>
                <td className={NUM}>{r.uses_30d}</td>
                <td className={NUM}>
                  {r.avg_cost_30d !== null ? formatEuros(r.avg_cost_30d) : "—"}
                </td>
              </tr>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-5 pb-3 text-xs text-slate-500">
        Le coût réel vient du journal des appels d&apos;IA, pour vous seul. Un
        prix à 0 rend l&apos;action gratuite.
      </p>
    </Card>
  );
}
