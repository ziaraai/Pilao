"use client";

import {
  AdminTitle,
  CELL,
  HEAD,
  JobIssues,
  Loaded,
  NUM,
  Pill,
} from "@/components/admin/ui";
import { Card, tableHead, tableRow } from "@/components/ui";
import { useAdminApi } from "@/lib/admin-auth";
import { formatDateTimeShort } from "@/lib/format";
import type { AdminSystem } from "@/lib/types";

const IMPORT_STATUS: Record<
  string,
  { label: string; tone: "ok" | "danger" | "warning" }
> = {
  done: { label: "Réussi", tone: "ok" },
  error: { label: "En erreur", tone: "danger" },
  running: { label: "En cours", tone: "warning" },
};

function duration(seconds: number | null): string {
  if (seconds == null) return "—";
  return seconds < 60
    ? `${seconds} s`
    : `${Math.floor(seconds / 60)} min ${String(seconds % 60).padStart(2, "0")}`;
}

/** US-6.2: the notice readers and the background jobs that need a look. Read-only. */
export default function AdminSystemPage() {
  const system = useAdminApi<AdminSystem>("/admin/system");
  return (
    <div className="space-y-6">
      <AdminTitle
        title="Technique"
        subtitle="Les imports d'annonces et les tâches de fond à regarder."
      />
      <Loaded state={system}>
        {(d) => (
          <>
            <Card
              title="Tâches en erreur ou bloquées"
              color="red"
              flush
              actions={<span className="text-sm font-medium">30 jours</span>}
            >
              {d.jobs.length === 0 ? (
                <p className="px-5 py-4 text-sm text-slate-600">
                  Aucune tâche en erreur ni bloquée.
                </p>
              ) : (
                <JobIssues jobs={d.jobs} />
              )}
            </Card>

            <Card
              title="Import des annonces"
              color="green"
              flush
              actions={
                <span className="text-sm font-medium">
                  les {d.imports.length} dernières passes
                </span>
              }
            >
              {d.imports.length === 0 ? (
                <p className="px-5 py-4 text-sm text-slate-600">
                  Aucune passe pour l&apos;instant.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className={tableHead}>
                        <th className={HEAD}>Source</th>
                        <th className={HEAD}>Début</th>
                        <th className={NUM}>Durée</th>
                        <th className={NUM}>Lues</th>
                        <th className={NUM}>Nouvelles</th>
                        <th className={NUM}>Mises à jour</th>
                        <th className={NUM}>Corrigées</th>
                        <th className={NUM}>Écartées</th>
                        <th className={HEAD}>État</th>
                      </tr>
                    </thead>
                    <tbody>
                      {d.imports.map((p, i) => {
                        const status = IMPORT_STATUS[p.status] ?? {
                          label: p.status,
                          tone: "warning" as const,
                        };
                        return (
                          <tr key={i} className={tableRow}>
                            <td className={`${CELL} font-semibold`}>
                              {p.source.toUpperCase()}
                            </td>
                            <td className={`${CELL} whitespace-nowrap`}>
                              {formatDateTimeShort(p.started_at)}
                            </td>
                            <td className={`${NUM} whitespace-nowrap`}>
                              {duration(p.duration_seconds)}
                            </td>
                            <td className={NUM}>{p.fetched}</td>
                            <td className={NUM}>{p.created}</td>
                            <td className={NUM}>{p.updated}</td>
                            <td className={NUM}>{p.corrected}</td>
                            <td className={NUM}>{p.skipped}</td>
                            <td className={CELL}>
                              <Pill tone={status.tone}>{status.label}</Pill>
                              {p.error && (
                                <span className="mt-1 block text-xs text-red-800">
                                  {p.error}
                                </span>
                              )}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
              )}
            </Card>
          </>
        )}
      </Loaded>
    </div>
  );
}
