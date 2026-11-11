"use client";

import Link from "next/link";
import { useParams, useRouter } from "next/navigation";
import { useState } from "react";

import { ConfirmDialog } from "@/components/admin/dialogs";
import { OrgUsers } from "@/components/admin/org-users";
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
import { Alert, Button, Card, tableHead, tableRow } from "@/components/ui";
import { monthLabel } from "@/lib/admin";
import { useAdminApi } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { formatDate, formatDateTimeShort, formatEuros } from "@/lib/format";
import { BID_STATUS, label } from "@/lib/labels";
import type {
  AdminDeletionPreview,
  AdminOrganizationDetail,
} from "@/lib/types";

type Open = "suspend" | "reactivate" | "delete" | "cancel" | null;

/** Lot 2: suspend, reactivate, delete, cancel a deletion — each in a confirmation window. */
function AccountActions({
  orgId,
  detail,
  onChanged,
}: {
  orgId: string;
  detail: AdminOrganizationDetail;
  onChanged: () => void;
}) {
  const router = useRouter();
  const [open, setOpen] = useState<Open>(null);
  const [preview, setPreview] = useState<AdminDeletionPreview | null>(null);
  const account = detail.account;
  const name = detail.identity.name;
  const base = `/admin/organizations/${orgId}`;

  async function askDeletion() {
    setPreview(await api<AdminDeletionPreview>(`${base}/deletion`));
    setOpen("delete");
  }

  return (
    <div className="flex flex-wrap gap-2">
      {account.suspended_at ? (
        <Button onClick={() => setOpen("reactivate")}>Réactiver</Button>
      ) : (
        <Button variant="danger" onClick={() => setOpen("suspend")}>
          Suspendre
        </Button>
      )}
      {account.deletion_due_at ? (
        <Button variant="secondary" onClick={() => setOpen("cancel")}>
          Annuler la suppression
        </Button>
      ) : (
        <Button variant="danger" onClick={askDeletion}>
          Supprimer
        </Button>
      )}

      {open === "suspend" && (
        <ConfirmDialog
          title={`Suspendre ${name}`}
          confirmLabel="Suspendre l'accès"
          danger
          needsReason
          onConfirm={({ reason }) =>
            api(`${base}/suspend`, { json: { reason } }).then(onChanged)
          }
          onClose={() => setOpen(null)}
        >
          <p>
            Ses utilisateurs sont déconnectés tout de suite et ne peuvent plus
            se connecter. Rien n&apos;est effacé ; plus aucun e-mail ne part
            pour l&apos;entreprise.
          </p>
        </ConfirmDialog>
      )}
      {open === "reactivate" && (
        <ConfirmDialog
          title={`Réactiver ${name}`}
          confirmLabel="Réactiver"
          onConfirm={() =>
            api(`${base}/reactivate`, { method: "POST" }).then(onChanged)
          }
          onClose={() => setOpen(null)}
        >
          <p>
            Ses utilisateurs pourront se connecter à nouveau, et la veille
            reprend.
          </p>
        </ConfirmDialog>
      )}
      {open === "delete" && preview && (
        <ConfirmDialog
          title={`Supprimer ${name}`}
          confirmLabel="Supprimer"
          danger
          needsName={name}
          needsCode
          onConfirm={async ({ name: typed, code }) => {
            const res = await api<{ mode: string }>(`${base}/deletion`, {
              json: { confirmation: typed, code },
            });
            if (res.mode === "immediate")
              router.replace(
                `/admin/entreprises?supprimee=${encodeURIComponent(name)}`,
              );
            else onChanged();
          }}
          onClose={() => setOpen(null)}
        >
          {preview.mode === "immediate" ? (
            <p>
              Personne ne s&apos;est jamais connecté à cet espace : il sera
              effacé <strong>tout de suite, définitivement</strong>.
            </p>
          ) : (
            <p>
              L&apos;accès sera suspendu tout de suite et toutes les données
              seront effacées le{" "}
              <strong>
                {preview.due_at ? formatDate(preview.due_at) : "—"}
              </strong>
              . Vous pourrez annuler d&apos;ici là. Ses utilisateurs sont
              prévenus par e-mail.
            </p>
          )}
        </ConfirmDialog>
      )}
      {open === "cancel" && (
        <ConfirmDialog
          title="Annuler la suppression"
          confirmLabel="Annuler la suppression"
          onConfirm={() =>
            api(`${base}/deletion`, { method: "DELETE" }).then(onChanged)
          }
          onClose={() => setOpen(null)}
        >
          <p>
            Rien ne sera effacé et ses utilisateurs sont prévenus.
            {account.suspended_at &&
              " L'entreprise reste suspendue : « Réactiver » pour lui rendre l'accès."}
          </p>
        </ConfirmDialog>
      )}
    </div>
  );
}

/** Suspended, deletion scheduled: said at the top of the page. */
function AccountState({ detail }: { detail: AdminOrganizationDetail }) {
  const a = detail.account;
  if (!a.suspended_at && !a.deletion_due_at) return null;
  return (
    <div className="space-y-3">
      {a.suspended_at && (
        <Alert tone="danger">
          <strong>Suspendue</strong> depuis le{" "}
          {formatDateTimeShort(a.suspended_at)}
          {a.suspension_reason && <> — raison : {a.suspension_reason}</>}
        </Alert>
      )}
      {a.deletion_due_at && (
        <Alert tone="warning">
          <strong>Suppression le {formatDate(a.deletion_due_at)}</strong>,{" "}
          {a.deletion_by === "pilao"
            ? "programmée par Pilao"
            : "demandée par l'entreprise"}
          .
        </Alert>
      )}
    </div>
  );
}

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

/** US-6.2 and lot 2: one company — identity, account, users, counters, costs — never its
 * documents. */
export default function AdminOrganizationPage() {
  const { id } = useParams<{ id: string }>();
  const detail = useAdminApi<AdminOrganizationDetail>(
    `/admin/organizations/${id}`,
  );

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
                readOnly={false}
                actions={
                  <AccountActions
                    orgId={id}
                    detail={d}
                    onChanged={detail.reload}
                  />
                }
                subtitle={
                  <>
                    Inscrite le {formatDate(i.created_at)} · dernière activité :{" "}
                    {i.last_activity_at
                      ? formatDateTimeShort(i.last_activity_at)
                      : "jamais"}
                    {d.account.suspended_at && (
                      <span className="ml-2">
                        <Pill tone="danger">Suspendue</Pill>
                      </span>
                    )}
                  </>
                }
              />
              <AccountState detail={d} />
              <p className="rounded-md border border-dashed border-slate-400 bg-white px-4 py-3 text-sm text-slate-700">
                Le contenu des mémoires, des DCE et des documents déposés
                n&apos;est jamais affiché ici. Cette consultation est
                enregistrée dans le journal (
                <Link
                  href={`/admin/journal?entreprise=${id}`}
                  className="font-semibold underline"
                >
                  voir le journal de cette entreprise
                </Link>
                ).
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

              <OrgUsers
                orgId={id}
                orgName={i.name}
                users={d.users}
                suspended={d.account.suspended_at !== null}
                onChanged={detail.reload}
              />

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
