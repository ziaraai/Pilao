"use client";

import Link from "next/link";

import {
  AdminTitle,
  CELL,
  HEAD,
  Loaded,
  NUM,
  Pill,
} from "@/components/admin/ui";
import { Card, tableHead, tableRow } from "@/components/ui";
import { useAdminApi } from "@/lib/admin-auth";
import { formatDate, formatDateTimeShort, formatEuros } from "@/lib/format";
import type { AdminOrganizationRow } from "@/lib/types";

/** US-6.2: every company on the platform, the last active first. Read-only. */
export default function AdminOrganizationsPage() {
  const list = useAdminApi<AdminOrganizationRow[]>("/admin/organizations");
  return (
    <div className="space-y-6">
      <AdminTitle
        title="Entreprises"
        subtitle="Toutes les entreprises inscrites, la dernière active en premier."
      />
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
                          {o.deletion_requested && (
                            <span className="ml-2">
                              <Pill tone="danger">Suppression demandée</Pill>
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
