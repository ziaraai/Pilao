"use client";

import Link from "next/link";
import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense } from "react";

import { AdminTitle, CELL, HEAD, Loaded } from "@/components/admin/ui";
import { Button, Card, Select, tableHead, tableRow } from "@/components/ui";
import { auditDetail, auditLabel } from "@/lib/admin";
import { useAdminApi } from "@/lib/admin-auth";
import { formatDateTimeShort } from "@/lib/format";
import type { AdminAuditPage, AdminOrganizationRow } from "@/lib/types";

const KINDS = [
  { value: "all", label: "Tout" },
  { value: "logins", label: "Connexions" },
  { value: "accounts", label: "Comptes" },
];

/** Lot 2, spec §2.6: every action and every sign-in of the administration. */
function Journal() {
  const params = useSearchParams();
  const router = useRouter();
  const pathname = usePathname();
  const kind = params.get("type") ?? "all";
  const org = params.get("entreprise") ?? "";
  const before = params.get("avant") ?? "";
  const query = new URLSearchParams({ kind });
  if (org) query.set("org_id", org);
  if (before) query.set("cursor", before);
  const page = useAdminApi<AdminAuditPage>(`/admin/audit?${query}`);
  const orgs = useAdminApi<AdminOrganizationRow[]>("/admin/organizations");

  function go(changes: Record<string, string>) {
    const next = new URLSearchParams(params);
    for (const [k, v] of Object.entries(changes))
      if (v) next.set(k, v);
      else next.delete(k);
    router.push(`${pathname}?${next}`);
  }

  return (
    <div className="space-y-6">
      <AdminTitle
        title="Journal"
        subtitle="Vos connexions et vos actions sur les comptes, les plus récentes en premier. Gardé 12 mois."
      />
      <div className="flex flex-wrap items-end gap-3">
        <div className="flex gap-1" role="group" aria-label="Type d'action">
          {KINDS.map((k) => (
            <Button
              key={k.value}
              variant={kind === k.value ? "primary" : "secondary"}
              aria-pressed={kind === k.value}
              onClick={() => go({ type: k.value, avant: "" })}
            >
              {k.label}
            </Button>
          ))}
        </div>
        <label className="text-sm font-medium text-slate-800">
          <span className="sr-only">Entreprise</span>
          <Select
            value={org}
            onChange={(e) => go({ entreprise: e.target.value, avant: "" })}
          >
            <option value="">Toutes les entreprises</option>
            {(orgs.data ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        </label>
      </div>
      <Loaded state={page}>
        {(p) => (
          <Card title="Lignes du journal" color="slate" flush>
            {p.rows.length === 0 ? (
              <p className="px-5 py-4 text-sm text-slate-600">
                Rien à afficher.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className={tableHead}>
                      <th className={HEAD}>Date</th>
                      <th className={HEAD}>Action</th>
                      <th className={HEAD}>Entreprise</th>
                      <th className={HEAD}>Détail</th>
                      <th className={HEAD}>Qui</th>
                      <th className={HEAD}>Adresse IP</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.rows.map((r) => (
                      <tr key={r.id} className={tableRow}>
                        <td className={`${CELL} whitespace-nowrap`}>
                          {formatDateTimeShort(r.at)}
                        </td>
                        <td className={`${CELL} font-semibold`}>
                          {auditLabel(r.action)}
                        </td>
                        <td className={CELL}>
                          {r.org_id === null ? (
                            "—"
                          ) : r.org_name ? (
                            <Link
                              href={`/admin/entreprises/${r.org_id}`}
                              className="underline"
                            >
                              {r.org_name}
                            </Link>
                          ) : (
                            <span className="text-slate-500">
                              Entreprise supprimée
                            </span>
                          )}
                        </td>
                        <td className={CELL}>{auditDetail(r.meta)}</td>
                        <td className={CELL}>{r.admin_email}</td>
                        <td className={`${CELL} whitespace-nowrap`}>
                          {r.ip ?? "—"}
                        </td>
                      </tr>
                    ))}
                  </tbody>
                </table>
              </div>
            )}
            {(p.next_cursor || before) && (
              <div className="flex flex-wrap gap-3 px-5 py-3">
                {before && (
                  <Button variant="secondary" onClick={() => go({ avant: "" })}>
                    Les plus récentes
                  </Button>
                )}
                {p.next_cursor && (
                  <Button
                    variant="secondary"
                    onClick={() => go({ avant: p.next_cursor ?? "" })}
                  >
                    Plus anciennes
                  </Button>
                )}
              </div>
            )}
          </Card>
        )}
      </Loaded>
    </div>
  );
}

export default function JournalPage() {
  return (
    <Suspense>
      <Journal />
    </Suspense>
  );
}
