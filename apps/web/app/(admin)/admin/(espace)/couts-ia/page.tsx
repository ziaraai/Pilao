"use client";

import Link from "next/link";
import { useState } from "react";

import {
  AdminTitle,
  CELL,
  HEAD,
  Loaded,
  NUM,
  Tile,
} from "@/components/admin/ui";
import { Card, Select, tableHead, tableRow } from "@/components/ui";
import { monthLabel } from "@/lib/admin";
import { formatEuros } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { AdminAiCosts } from "@/lib/types";

const number = new Intl.NumberFormat("fr-FR");
const Empty = () => (
  <p className="px-5 py-4 text-sm text-slate-600">Aucun appel ce mois-là.</p>
);

/** US-6.2: what the AI cost over one month, by company, task and model. Read-only. */
export default function AdminAiCostsPage() {
  const [month, setMonth] = useState<string | null>(null);
  const costs = useApi<AdminAiCosts>(
    month ? `/admin/ai-costs?month=${month}` : "/admin/ai-costs",
  );

  return (
    <div className="space-y-6">
      <AdminTitle
        title="Coûts de l'IA"
        subtitle="Ce que l'IA a coûté sur un mois, par entreprise, par tâche et par modèle."
        actions={
          costs.data && (
            <label className="flex items-center gap-2 text-sm font-medium text-slate-800">
              Mois
              <Select
                className="w-44"
                value={month ?? costs.data.month}
                onChange={(e) => setMonth(e.target.value)}
              >
                {costs.data.months.map((m) => (
                  <option key={m} value={m}>
                    {monthLabel(m)}
                  </option>
                ))}
              </Select>
            </label>
          )
        }
      />
      <Loaded state={costs}>
        {(d) => (
          <>
            <div className="grid grid-cols-2 gap-3 sm:grid-cols-3">
              <Tile
                value={formatEuros(d.total)}
                label={`coût total, ${monthLabel(d.month)}`}
                color="amber"
              />
              <Tile
                value={number.format(
                  d.by_model.reduce((sum, m) => sum + m.calls, 0),
                )}
                label="appels à l'IA"
                color="blue"
              />
              <Tile
                value={d.by_org.filter((o) => o.org_id).length}
                label="entreprises concernées"
                color="brand"
              />
            </div>

            <Card title="Par entreprise" color="brand" flush>
              {d.by_org.length === 0 ? (
                <Empty />
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className={tableHead}>
                        <th className={HEAD}>Entreprise</th>
                        <th className={NUM}>Appels</th>
                        <th className={NUM}>Jetons lus</th>
                        <th className={NUM}>Jetons écrits</th>
                        <th className={NUM}>Coût</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.by_org.map((o) => (
                        <tr key={o.org_id ?? "platform"} className={tableRow}>
                          <td className={CELL}>
                            {o.org_id ? (
                              <Link
                                href={`/admin/entreprises/${o.org_id}`}
                                className="font-semibold text-brand-navy underline"
                              >
                                {o.name}
                              </Link>
                            ) : (
                              <span className="italic text-slate-700">
                                {o.name} (hors entreprise)
                              </span>
                            )}
                          </td>
                          <td className={NUM}>{number.format(o.calls)}</td>
                          <td className={NUM}>
                            {number.format(o.input_tokens)}
                          </td>
                          <td className={NUM}>
                            {number.format(o.output_tokens)}
                          </td>
                          <td className={`${NUM} font-semibold`}>
                            {formatEuros(o.cost)}
                          </td>
                        </tr>
                      ))}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>

            <div className="grid grid-cols-1 gap-6 2xl:grid-cols-2">
              <Card title="Par tâche" color="amber" flush>
                {d.by_task.length === 0 ? (
                  <Empty />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className={tableHead}>
                          <th className={HEAD}>Tâche</th>
                          <th className={NUM}>Appels</th>
                          <th className={NUM}>Échecs</th>
                          <th className={NUM}>Durée moyenne</th>
                          <th className={NUM}>Coût</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.by_task.map((t) => (
                          <tr key={t.task} className={tableRow}>
                            <td className={CELL}>{t.label}</td>
                            <td className={NUM}>{number.format(t.calls)}</td>
                            <td
                              className={`${NUM} ${t.failures ? "font-semibold text-red-700" : ""}`}
                            >
                              {t.failures}
                            </td>
                            <td className={NUM}>
                              {(t.avg_latency_ms / 1000)
                                .toFixed(1)
                                .replace(".", ",")}{" "}
                              s
                            </td>
                            <td className={`${NUM} font-semibold`}>
                              {formatEuros(t.cost)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <Card title="Par modèle" color="slate" flush>
                {d.by_model.length === 0 ? (
                  <Empty />
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className={tableHead}>
                          <th className={HEAD}>Modèle</th>
                          <th className={NUM}>Appels</th>
                          <th className={NUM}>Coût</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.by_model.map((m) => (
                          <tr key={m.model} className={tableRow}>
                            <td
                              className={`${CELL} break-all font-mono text-xs`}
                            >
                              {m.model}
                            </td>
                            <td className={NUM}>{number.format(m.calls)}</td>
                            <td className={`${NUM} font-semibold`}>
                              {formatEuros(m.cost)}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>
            </div>
          </>
        )}
      </Loaded>
    </div>
  );
}
