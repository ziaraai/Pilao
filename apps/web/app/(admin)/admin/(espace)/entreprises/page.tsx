"use client";

import Link from "next/link";
import { useSearchParams } from "next/navigation";
import { Suspense } from "react";

import {
  AdminTitle,
  CELL,
  HEAD,
  Loaded,
  NUM,
  Pill,
} from "@/components/admin/ui";
import { Alert, Card, tableHead, tableRow } from "@/components/ui";
import { moduleShort } from "@/lib/admin";
import { useAdminApi } from "@/lib/admin-auth";
import { formatDate, formatDateTimeShort, formatEuros } from "@/lib/format";
import type { AdminOrganizationRow } from "@/lib/types";

/** After an immediate deletion, the company page sends here with its name. */
function DeletedNotice() {
  const name = useSearchParams().get("supprimee");
  return name ? <Alert tone="ok">{name} a été supprimée.</Alert> : null;
}

/** US-6.2 and lot 2: every company on the platform, the last active first. */
export default function AdminOrganizationsPage() {
  const list = useAdminApi<AdminOrganizationRow[]>("/admin/organizations");
  return (
    <div className="space-y-6">
      <AdminTitle
        title="Entreprises"
        readOnly={false}
        subtitle="Toutes les entreprises inscrites, la dernière active en premier."
        actions={
          <Link
            href="/admin/entreprises/nouvelle"
            className="inline-flex items-center rounded-md bg-brand-navy px-3.5 py-2 text-sm font-semibold text-white hover:bg-[#0a2a63]"
          >
            Créer une entreprise
          </Link>
        }
      />
      <Suspense>
        <DeletedNotice />
      </Suspense>
      <Loaded state={list}>
        {(rows) => (
          <Card
            title="Entreprises inscrites"
            color="brand"
            flush
            actions={<span className="text-sm font-medium">{rows.length}</span>}
          >
            {rows.length === 0 ? (
              <p className="px-5 py-4 text-sm text-slate-600">
                Aucune entreprise inscrite pour l&apos;instant.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className={tableHead}>
                      <th className={HEAD}>Entreprise</th>
                      <th className={HEAD}>Ville</th>
                      <th className={HEAD}>Inscrite le</th>
                      <th className={NUM}>Utilisateurs</th>
                      <th className={HEAD}>Dernière activité</th>
                      <th className={NUM}>Dossiers</th>
                      <th className={NUM}>Mémoires</th>
                      <th className={NUM}>Profil</th>
                      <th className={NUM}>IA ce mois</th>
                      <th className={HEAD}>Modules</th>
                      <th className={HEAD}>Formule</th>
                      <th className={NUM}>Crédits</th>
                    </tr>
                  </thead>
                  <tbody>
                    {rows.map((o) => (
                      <tr key={o.id} className={tableRow}>
                        <td className={CELL}>
                          <Link
                            href={`/admin/entreprises/${o.id}`}
                            className="whitespace-nowrap font-semibold text-brand-navy underline"
                          >
                            {o.name}
                          </Link>
                          <span className="ml-2 inline-flex flex-wrap gap-1 align-middle">
                            {o.suspended && (
                              <Pill tone="danger">
                                Suspendue
                                {o.suspended_at
                                  ? ` le ${formatDate(o.suspended_at)}`
                                  : ""}
                              </Pill>
                            )}
                            {o.deletion_due_at && (
                              <Pill tone="warning">
                                Suppression le {formatDate(o.deletion_due_at)}
                              </Pill>
                            )}
                            {o.invitation_pending && (
                              <Pill tone="neutral">Invitation en attente</Pill>
                            )}
                          </span>
                          {o.suspension_reason && (
                            <span className="mt-1 block text-xs text-red-700">
                              Raison : {o.suspension_reason}
                            </span>
                          )}
                        </td>
                        <td className={CELL}>{o.city ?? "—"}</td>
                        <td className={`${CELL} whitespace-nowrap`}>
                          {formatDate(o.created_at)}
                        </td>
                        <td className={NUM}>{o.users}</td>
                        <td className={`${CELL} whitespace-nowrap`}>
                          {o.last_activity_at
                            ? formatDateTimeShort(o.last_activity_at)
                            : "Jamais"}
                        </td>
                        <td className={NUM}>{o.bids}</td>
                        <td className={NUM}>{o.memoirs}</td>
                        <td className={NUM}>{o.completeness_pct} %</td>
                        <td className={NUM}>{formatEuros(o.ai_cost_month)}</td>
                        <td className={CELL}>
                          <span className="inline-flex flex-wrap gap-1">
                            {o.modules.length === 0 ? (
                              <Pill tone="neutral">Aucun</Pill>
                            ) : (
                              o.modules.map((m) => (
                                <Pill key={m} tone="ok">
                                  {moduleShort(m)}
                                </Pill>
                              ))
                            )}
                          </span>
                        </td>
                        <td className={`${CELL} whitespace-nowrap`}>
                          {o.plan.name}
                        </td>
                        <td
                          className={`${NUM} ${o.credits_total === 0 ? "font-semibold text-red-700" : ""}`}
                        >
                          {o.credits_total}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
          </Card>
        )}
      </Loaded>
    </div>
  );
}
