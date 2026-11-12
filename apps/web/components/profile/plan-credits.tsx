"use client";

import { Alert, Card, Loading, tableHead, tableRow } from "@/components/ui";
import { useMe } from "@/lib/auth";
import { credits } from "@/lib/credits";
import { formatDate, formatDateTimeShort } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { moduleName } from "@/lib/modules";
import type { CreditLine, Credits } from "@/lib/types";

function what(line: CreditLine): string {
  if (line.kind === "welcome") return "Crédits offerts";
  if (line.kind === "grant") return "Crédits ajoutés par Pilao";
  if (line.kind === "refund") return line.reason ?? "Remboursé";
  return line.action_name ?? "Action";
}

/** Profil, « Formule et crédits » (lot 4): the plan, the balance, the prices, the history. */
export function PlanCredits() {
  const { me } = useMe();
  const data = useApi<Credits>("/credits");
  if (data.error && !data.data)
    return <Alert tone="danger">{data.error}</Alert>;
  if (!data.data) return <Loading />;
  const c = data.data;
  const contact = me.support_email
    ? `contactez Pilao : ${me.support_email}.`
    : "contactez Pilao.";
  return (
    <div className="space-y-6">
      <div className="grid grid-cols-1 gap-6 lg:grid-cols-2">
        <Card title="Votre formule" color="brand">
          <p className="text-lg font-bold text-brand-navy">{c.plan.name}</p>
          {c.plan.description && (
            <p className="mt-1 text-sm text-slate-700">{c.plan.description}</p>
          )}
          <p className="mt-3 text-sm text-slate-700">
            Modules :{" "}
            {c.plan.modules.length
              ? c.plan.modules.map(moduleName).join(", ")
              : "aucun"}
          </p>
          <p className="mt-3 text-sm text-slate-600">
            Pour changer de formule ou ajouter des crédits, {contact}
          </p>
        </Card>
        <Card title="Vos crédits" color="violet">
          <p className="text-3xl font-bold text-violet-800">
            {credits(c.total)}
            <span className="ml-2 text-base font-medium text-slate-600">
              restants
            </span>
          </p>
          <ul className="mt-3 space-y-1 text-sm text-slate-700">
            {c.monthly_allowance > 0 ? (
              <>
                <li>
                  Crédits du mois : {c.monthly_left} sur {c.monthly_allowance},
                  renouvelés le {formatDate(c.renews_on)}
                </li>
                <li>Crédits supplémentaires : {c.extra}</li>
              </>
            ) : (
              <li>Crédits offerts et ajoutés : {c.extra}</li>
            )}
          </ul>
        </Card>
      </div>
      <Card title="Prix des actions" color="slate" flush>
        <ul className="divide-y divide-slate-200">
          {c.prices.map((p) => (
            <li
              key={p.action}
              className="flex items-center justify-between gap-3 px-5 py-2.5 text-sm"
            >
              <span className="text-slate-800">{p.name}</span>
              <span className="font-semibold text-slate-900">
                {p.credits > 0 ? credits(p.credits) : "Gratuit"}
              </span>
            </li>
          ))}
        </ul>
        <p className="px-5 pb-3 text-xs text-slate-500">
          Une action qui échoue rend ses crédits. Relancer un chapitre en erreur
          est gratuit.
        </p>
      </Card>
      <Card title="Historique" color="slate" flush>
        {c.history.length === 0 ? (
          <p className="px-5 py-4 text-sm text-slate-600">Aucun mouvement.</p>
        ) : (
          <div className="overflow-x-auto">
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
                    <td className="px-4 py-2">{what(h)}</td>
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
      </Card>
    </div>
  );
}
