"use client";

import { useState } from "react";

import {
  AdminTitle,
  CELL,
  FeedbackList,
  HEAD,
  Loaded,
  NUM,
} from "@/components/admin/ui";
import { Card, tableHead, tableRow } from "@/components/ui";
import { useAdminApi } from "@/lib/admin-auth";
import { formatDuration } from "@/lib/format";
import type { AdminFeedback } from "@/lib/types";

const WINDOWS = [7, 30, 90];

/** US-6.2: what the testers wrote from the application, and the time saved. Read-only. */
export default function AdminFeedbackPage() {
  const [days, setDays] = useState(30);
  const feedback = useAdminApi<AdminFeedback>(`/admin/feedback?days=${days}`);

  return (
    <div className="space-y-6">
      <AdminTitle
        title="Avis des testeurs"
        subtitle="Ce que les utilisateurs ont écrit depuis l'application, et le temps qu'ils ont gagné."
        actions={
          <div
            role="group"
            aria-label="Période"
            className="inline-flex overflow-hidden rounded-md ring-1 ring-inset ring-slate-400"
          >
            {WINDOWS.map((w) => (
              <button
                key={w}
                type="button"
                aria-pressed={days === w}
                onClick={() => setDays(w)}
                className={`px-3 py-1.5 text-sm font-semibold ${days === w ? "bg-brand-navy text-white" : "bg-white text-brand-navy hover:bg-slate-50"}`}
              >
                {w} jours
              </button>
            ))}
          </div>
        }
      />
      <Loaded state={feedback}>
        {(d) => (
          <>
            <Card
              title={`Avis des ${d.days} derniers jours`}
              color="violet"
              flush
              actions={
                <span className="text-sm font-medium">{d.items.length}</span>
              }
            >
              {d.items.length === 0 ? (
                <p className="px-5 py-4 text-sm text-slate-600">
                  Aucun avis sur cette période.
                </p>
              ) : (
                <FeedbackList items={d.items} />
              )}
            </Card>

            <Card title="Temps gagné par les testeurs" color="green" flush>
              {d.time_saved.length === 0 ? (
                <p className="px-5 py-4 text-sm text-slate-600">
                  Aucun dossier avec ses deux durées saisies pour
                  l&apos;instant.
                </p>
              ) : (
                <div className="overflow-x-auto">
                  <table className="w-full text-sm">
                    <thead>
                      <tr className={tableHead}>
                        <th className={HEAD}>Entreprise</th>
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
          </>
        )}
      </Loaded>
    </div>
  );
}
