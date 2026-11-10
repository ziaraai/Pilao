"use client";

import Link from "next/link";
import { useParams } from "next/navigation";

import {
  AdminTitle,
  CELL,
  FeedbackList,
  HEAD,
  JobIssues,
  Loaded,
  NUM,
  Pill,
  Tile,
} from "@/components/admin/ui";
import { Card, tableHead, tableRow } from "@/components/ui";
import { monthLabel } from "@/lib/admin";
import { formatDate, formatDateTimeShort, formatEuros } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { BID_STATUS, ROLES, label } from "@/lib/labels";
import type { AdminOrganizationDetail } from "@/lib/types";

/** The cost of the last six months, as bars. */
function CostBars({
  months,
}: {
  months: AdminOrganizationDetail["ai_months"];
}) {
  const highest = Math.max(...months.map((m) => Number(m.cost)), 0.01);
  return (
    <div className="flex items-end gap-2 px-5 pb-3 pt-5" aria-hidden="true">
      {months.map((m) => (
        <div
          key={m.month}
          className="flex min-w-0 flex-1 flex-col items-center"
        >
          <span className="mb-1 text-[11px] font-semibold text-slate-700">
            {formatEuros(m.cost)}
          </span>
          <span
            className="w-full rounded-t border border-emerald-500 bg-emerald-200"
            style={{
              height: `${Math.max(2, (Number(m.cost) / highest) * 72)}px`,
            }}
          />
          <span className="mt-1 truncate text-[11px] text-slate-500">
            {monthLabel(m.month).split(" ")[0]}
          </span>
        </div>
      ))}
    </div>
  );
}

/** US-6.2: one company. Identity, users, counters, costs — never its documents. */
export default function AdminOrganizationPage() {
  const { id } = useParams<{ id: string }>();
  const detail = useApi<AdminOrganizationDetail>(`/admin/organizations/${id}`);

  return (
    <div>
      <p className="mb-2 text-sm text-slate-600">
        <Link href="/admin/entreprises" className="underline">
          Entreprises
        </Link>{" "}
        ›
      </p>
      <Loaded state={detail}>
        {(d) => {
          const i = d.identity;
          const c = d.counters;
          return (
            <div className="space-y-6">
              <AdminTitle
                title={i.name}
                subtitle={
                  <>
                    Inscrite le {formatDate(i.created_at)} · dernière activité :{" "}
                    {i.last_activity_at
                      ? formatDateTimeShort(i.last_activity_at)
                      : "jamais"}
                    {i.deletion_requested && (
                      <span className="ml-2">
                        <Pill tone="danger">Suppression demandée</Pill>
                      </span>
                    )}
                  </>
                }
              />
              <p className="rounded-md border border-dashed border-slate-400 bg-white px-4 py-3 text-sm text-slate-700">
                Le contenu des mémoires, des DCE et des documents déposés
                n&apos;est jamais affiché ici. Cette consultation est
                enregistrée dans le journal.
              </p>

              <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-5">
                <Tile value={c.bids} label="dossiers" color="blue" />
                <Tile
                  value={c.memoirs_done}
                  label="mémoires rédigés"
                  color="violet"
                />
                <Tile
                  value={c.knowledge_documents}
                  label="documents dans la base"
                  color="sky"
                />
                <Tile
                  value={`${c.completeness_pct} %`}
                  label="profil complété"
                  color="brand"
                />
                <Tile
                  value={formatEuros(c.ai_cost_month)}
                  label="coût de l'IA ce mois"
                  color="amber"
                />
              </div>

              <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                <Card title="Identité" color="brand">
                  <dl className="grid grid-cols-[9rem_1fr] gap-x-3 gap-y-2 text-sm">
                    <dt className="text-slate-500">SIRET</dt>
                    <dd className="font-semibold">{i.siret}</dd>
                    <dt className="text-slate-500">Forme juridique</dt>
                    <dd className="font-semibold">{i.legal_form ?? "—"}</dd>
                    <dt className="text-slate-500">Code NAF</dt>
                    <dd className="font-semibold">{i.naf_code ?? "—"}</dd>
                    <dt className="text-slate-500">Ville</dt>
                    <dd className="font-semibold">
                      {[i.postal_code, i.city].filter(Boolean).join(" ") || "—"}
                    </dd>
                    <dt className="text-slate-500">Métiers</dt>
                    <dd className="font-semibold">
                      {i.trades.map((t) => t.replace(/_/g, " ")).join(", ") ||
                        "—"}
                    </dd>
                    <dt className="text-slate-500">Départements</dt>
                    <dd className="font-semibold">
                      {i.departments.join(", ") || "—"}
                    </dd>
                    <dt className="text-slate-500">Dossiers</dt>
                    <dd className="font-semibold">
                      {Object.entries(c.bids_by_status)
                        .map(
                          ([s, n]) =>
                            `${n} ${label(BID_STATUS, s).toLowerCase()}`,
                        )
                        .join(", ") || "aucun"}
                    </dd>
                    <dt className="text-slate-500">Attestations</dt>
                    <dd className="font-semibold">
                      {c.compliance_valid} valide
                      {c.compliance_valid > 1 ? "s" : ""},{" "}
                      {c.compliance_expired} expirée
                      {c.compliance_expired > 1 ? "s" : ""}
                    </dd>
                  </dl>
                </Card>

                <Card title="Coût de l'IA par mois" color="amber" flush>
                  <CostBars months={d.ai_months} />
                  <p className="sr-only">
                    {d.ai_months
                      .map(
                        (m) =>
                          `${monthLabel(m.month)} : ${formatEuros(m.cost)}`,
                      )
                      .join(" ; ")}
                  </p>
                  {d.ai_tasks.length > 0 && (
                    <table className="w-full text-sm">
                      <thead>
                        <tr className={tableHead}>
                          <th className={HEAD}>Tâche, ce mois</th>
                          <th className={NUM}>Appels</th>
                          <th className={NUM}>Coût</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.ai_tasks.map((t) => (
                          <tr key={t.task} className={tableRow}>
                            <td className={CELL}>{t.label}</td>
                            <td className={NUM}>{t.calls}</td>
                            <td className={NUM}>{formatEuros(t.cost)}</td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  )}
                </Card>
              </div>

              <Card
                title="Utilisateurs"
                color="blue"
                flush
                actions={
                  <span className="text-sm font-medium">{d.users.length}</span>
                }
              >
                {d.users.length === 0 ? (
                  <p className="px-5 py-4 text-sm text-slate-600">
                    Aucun utilisateur.
                  </p>
                ) : (
                  <div className="overflow-x-auto">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className={tableHead}>
                          <th className={HEAD}>Nom</th>
                          <th className={HEAD}>E-mail</th>
                          <th className={HEAD}>Rôle</th>
                          <th className={HEAD}>E-mail vérifié</th>
                          <th className={HEAD}>Dernière connexion</th>
                          <th className={HEAD}>Conditions</th>
                        </tr>
                      </thead>
                      <tbody>
                        {d.users.map((u) => (
                          <tr key={u.email} className={tableRow}>
                            <td className={`${CELL} font-semibold`}>
                              {u.full_name ?? "—"}
                            </td>
                            <td className={CELL}>{u.email}</td>
                            <td className={CELL}>{label(ROLES, u.role)}</td>
                            <td className={CELL}>
                              {u.email_verified ? "Oui" : "Non"}
                            </td>
                            <td className={`${CELL} whitespace-nowrap`}>
                              {u.last_login_at
                                ? formatDateTimeShort(u.last_login_at)
                                : "Jamais"}
                            </td>
                            <td className={CELL}>
                              {u.terms_version
                                ? `version ${u.terms_version}`
                                : "non acceptées"}
                            </td>
                          </tr>
                        ))}
                      </tbody>
                    </table>
                  </div>
                )}
              </Card>

              <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
                <Card
                  title="Tâches en erreur"
                  color="red"
                  flush
                  actions={
                    <span className="text-sm font-medium">30 jours</span>
                  }
                >
                  {d.job_errors.length === 0 ? (
                    <p className="px-5 py-4 text-sm text-slate-600">
                      Aucune erreur.
                    </p>
                  ) : (
                    <JobIssues jobs={d.job_errors} showCompany={false} />
                  )}
                </Card>
                <Card
                  title="Avis laissés"
                  color="violet"
                  flush
                  actions={
                    <span className="text-sm font-medium">
                      {d.feedback.length}
                    </span>
                  }
                >
                  {d.feedback.length === 0 ? (
                    <p className="px-5 py-4 text-sm text-slate-600">
                      Aucun avis.
                    </p>
                  ) : (
                    <FeedbackList items={d.feedback} showCompany={false} />
                  )}
                </Card>
              </div>
            </div>
          );
        }}
      </Loaded>
    </div>
  );
}
