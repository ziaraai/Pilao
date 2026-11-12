"use client";

import Link from "next/link";

import { AdminTitle, CELL, NUM, Pill, Tile } from "@/components/admin/ui";
import { Alert, Card, Loading, tableHead, tableRow } from "@/components/ui";
import { useAdmin, useAdminApi } from "@/lib/admin-auth";
import { formatDateTimeShort, formatDuration, formatEuros } from "@/lib/format";
import type { AdminOverview, AdminWatchItem } from "@/lib/types";

const today = new Intl.DateTimeFormat("fr-FR", {
  weekday: "long",
  day: "numeric",
  month: "long",
  timeZone: "Europe/Paris",
});

/** Where a line of « À surveiller » leads. */
function watchLink(item: AdminWatchItem): { href: string; label: string } {
  if ((item.kind === "inactive" || item.kind === "credits") && item.org_id)
    return {
      href: `/admin/entreprises/${item.org_id}`,
      label: "Voir la fiche",
    };
  if (item.kind === "ai") return { href: "/admin/couts-ia", label: "Voir" };
  if (item.kind === "settings")
    return { href: "/admin/reglages", label: "Voir les réglages" };
  return { href: "/admin/technique", label: "Voir" };
}

/** US-6.2: everything that happens on the platform, at a glance. Read-only. */
export default function AdminOverviewPage() {
  const { me } = useAdmin();
  const overview = useAdminApi<AdminOverview>("/admin/overview");
  if (overview.error && !overview.data)
    return <Alert tone="danger">{overview.error}</Alert>;
  if (!overview.data) return <Loading />;
  const d = overview.data;
  const c = d.counters;
  const day = today.format(new Date());

  return (
    <div className="space-y-6">
      <AdminTitle
        title="Vue d'ensemble"
        subtitle={
          <>
            {day.charAt(0).toUpperCase() + day.slice(1)}
            {me.previous_login_at && (
              <>
                {" "}
                · Votre connexion précédente :{" "}
                {formatDateTimeShort(me.previous_login_at)}
              </>
            )}
          </>
        }
      />
      {me.recovery_codes_left < 8 && (
        <Alert tone={me.recovery_codes_left < 3 ? "warning" : "info"}>
          Il vous reste {me.recovery_codes_left} code
          {me.recovery_codes_left > 1 ? "s" : ""} de secours.
        </Alert>
      )}

      <div className="grid grid-cols-2 gap-3 sm:grid-cols-3 xl:grid-cols-6">
        <Tile
          value={c.organizations}
          label="entreprises inscrites"
          color="brand"
          href="/admin/entreprises"
        />
        <Tile value={c.active_7d} label="actives sur 7 jours" color="green" />
        <Tile value={c.bids_open} label="dossiers en cours" color="blue" />
        <Tile value={c.memoirs_done} label="mémoires rédigés" color="violet" />
        <Tile
          value={formatEuros(c.ai_cost_month)}
          label="coût de l'IA ce mois"
          color="amber"
          href="/admin/couts-ia"
        />
        <Tile
          value={c.job_errors_24h}
          label="tâches en erreur (24 h)"
          color={c.job_errors_24h ? "red" : "slate"}
          href="/admin/technique"
        />
      </div>

      <Card
        title="À surveiller"
        color="red"
        flush
        actions={
          d.watch.length > 0 && (
            <span className="text-sm font-medium">
              {d.watch.length} point{d.watch.length > 1 ? "s" : ""}
            </span>
          )
        }
      >
        {d.watch.length === 0 ? (
          <p className="px-5 py-4 text-sm text-slate-700">Tout va bien.</p>
        ) : (
          <ul>
            {d.watch.map((item, i) => {
              const link = watchLink(item);
              return (
                <li
                  key={i}
                  className={`flex flex-wrap items-center gap-x-3 gap-y-1 px-5 py-3 text-sm ${tableRow}`}
                >
                  <span
                    className={`h-2.5 w-2.5 shrink-0 rounded-full ${item.level === "red" ? "bg-red-500" : "bg-amber-500"}`}
                    aria-hidden="true"
                  />
                  <span className="min-w-0 flex-1">
                    <strong className="text-slate-900">{item.title}</strong>
                    {item.detail && (
                      <span className="text-slate-700"> — {item.detail}</span>
                    )}
                  </span>
                  <span className="w-full whitespace-nowrap pl-5 text-xs text-slate-500 sm:w-auto sm:pl-0">
                    {item.at && <>{formatDateTimeShort(item.at)} · </>}
                    <Link
                      href={link.href}
                      className="font-semibold text-brand-navy underline"
                    >
                      {link.label}
                    </Link>
                  </span>
                </li>
              );
            })}
            {d.more_job_issues > 0 && (
              <li className="px-5 py-3 text-sm text-slate-600">
                et {d.more_job_issues} autre{d.more_job_issues > 1 ? "s" : ""}{" "}
                tâche{d.more_job_issues > 1 ? "s" : ""} :{" "}
                <Link
                  href="/admin/technique"
                  className="font-semibold text-brand-navy underline"
                >
                  tout voir
                </Link>
              </li>
            )}
          </ul>
        )}
      </Card>

      <Card title="Activité des 7 derniers jours" color="blue" flush>
        {d.activity.length === 0 ? (
          <p className="px-5 py-4 text-sm text-slate-600">
            Aucune entreprise inscrite pour l&apos;instant.
          </p>
        ) : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={tableHead}>
                  <th className={`${CELL} text-left`}>Entreprise</th>
                  <th className={NUM}>Connexions</th>
                  <th className={NUM}>Dossiers</th>
                  <th className={NUM}>Mémoires</th>
                  <th className={NUM}>Exports</th>
                </tr>
              </thead>
              <tbody>
                {d.activity.map((a) => (
                  <tr key={a.org_id} className={tableRow}>
                    <td className={CELL}>
                      <Link
                        href={`/admin/entreprises/${a.org_id}`}
                        className="font-semibold text-brand-navy underline"
                      >
                        {a.name}
                      </Link>
                    </td>
                    <td className={NUM}>{a.logins}</td>
                    <td className={NUM}>{a.bids}</td>
                    <td className={NUM}>{a.memoirs}</td>
                    <td className={NUM}>{a.exports}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </Card>

      <div className="grid grid-cols-1 gap-6 2xl:grid-cols-2">
        <Card
          title="Import des annonces"
          color="green"
          flush
          actions={
            <span className="text-sm font-medium">toutes les 2 heures</span>
          }
        >
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className={tableHead}>
                  <th className={`${CELL} text-left`}>Source</th>
                  <th className={`${CELL} text-left`}>Dernière passe</th>
                  <th className={NUM}>Lues</th>
                  <th className={NUM}>Nouvelles</th>
                  <th className={`${CELL} text-left`}>État</th>
                </tr>
              </thead>
              <tbody>
                {d.imports.map((imp) => (
                  <tr key={imp.source} className={tableRow}>
                    <td className={`${CELL} font-semibold`}>
                      {imp.source.toUpperCase()}
                    </td>
                    <td className={`${CELL} whitespace-nowrap`}>
                      {formatDateTimeShort(imp.started_at)}
                    </td>
                    <td className={NUM}>{imp.fetched ?? "—"}</td>
                    <td className={NUM}>{imp.created ?? "—"}</td>
                    <td className={CELL}>
                      {!imp.enabled ? (
                        <Pill tone="neutral">Désactivé</Pill>
                      ) : imp.status === "done" ? (
                        <Pill tone="ok">Réussi</Pill>
                      ) : imp.status === "error" ? (
                        <Pill tone="danger">En erreur</Pill>
                      ) : imp.status === "running" ? (
                        <Pill tone="warning">En cours</Pill>
                      ) : (
                        <Pill tone="neutral">Jamais passé</Pill>
                      )}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </Card>

        <Card title="Temps gagné par les testeurs" color="violet" flush>
          {d.time_saved.length === 0 ? (
            <p className="px-5 py-4 text-sm text-slate-600">
              Aucun dossier avec ses deux durées saisies pour l&apos;instant.
            </p>
          ) : (
            <div className="overflow-x-auto">
              <table className="w-full text-sm">
                <thead>
                  <tr className={tableHead}>
                    <th className={`${CELL} text-left`}>Entreprise</th>
                    <th className={NUM}>Dossiers</th>
                    <th className={NUM}>Temps gagné</th>
                  </tr>
                </thead>
                <tbody>
                  {d.time_saved.map((t) => (
                    <tr key={t.name} className={tableRow}>
                      <td className={CELL}>{t.name}</td>
                      <td className={NUM}>{t.bids}</td>
                      <td className={NUM}>
                        {formatDuration(Math.max(0, t.minutes_saved))}
                        {t.percent != null && ` (${t.percent} %)`}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </Card>
      </div>
    </div>
  );
}
