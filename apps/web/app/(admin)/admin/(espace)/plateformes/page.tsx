"use client";

import { useState } from "react";

import { AdminTitle, CELL, HEAD, Loaded, NUM } from "@/components/admin/ui";
import {
  Badge,
  Card,
  Field,
  Select,
  tableHead,
  tableRow,
} from "@/components/ui";
import { useAdminApi } from "@/lib/admin-auth";
import type { Tone } from "@/lib/labels";
import type { AdminDcePlatforms, AdminOrganizationRow } from "@/lib/types";

const WINDOWS = [30, 90, 365];
const RETRIEVAL: Record<string, { label: string; tone: Tone }> = {
  robot: { label: "Robot", tone: "ok" },
  guided: { label: "Guidé", tone: "warning" },
  none: { label: "Pas de lien", tone: "neutral" },
};

/**
 * « Plateformes des DCE » (24/11): on which buyers' platforms the DCE of the notices and of the
 * dossiers are, to know where the robot or the e-mail address would bring the most. Read-only.
 */
export default function AdminPlatformsPage() {
  const [days, setDays] = useState(90);
  const [org, setOrg] = useState("");
  const orgs = useAdminApi<AdminOrganizationRow[]>("/admin/organizations");
  const data = useAdminApi<AdminDcePlatforms>(
    `/admin/dce-platforms?days=${days}${org ? `&org_id=${org}` : ""}`,
  );

  return (
    <div className="space-y-6">
      <AdminTitle
        title="Plateformes des DCE"
        subtitle="Où sont les DCE des annonces et des dossiers, et comment Pilao les obtient : par le robot (PLACE, Atexo) ou guidé (l'utilisateur dépose le DCE)."
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
      <div className="max-w-sm">
        <Field label="Entreprise" htmlFor="platform-org">
          <Select
            id="platform-org"
            value={org}
            onChange={(e) => setOrg(e.target.value)}
          >
            <option value="">Toutes les entreprises</option>
            {(orgs.data ?? []).map((o) => (
              <option key={o.id} value={o.id}>
                {o.name}
              </option>
            ))}
          </Select>
        </Field>
      </div>
      <Loaded state={data}>
        {(d) => (
          <Card
            title={`Sur ${d.days} jours`}
            color="blue"
            flush
            actions={
              <span className="text-sm font-medium">
                {d.totals.dossiers === 0
                  ? "Aucun dossier"
                  : `${d.totals.robot_dossiers} dossier${d.totals.robot_dossiers > 1 ? "s" : ""} sur ${d.totals.dossiers} récupérable${d.totals.dossiers > 1 ? "s" : ""} par le robot`}
              </span>
            }
          >
            {d.rows.length === 0 ? (
              <p className="px-5 py-4 text-sm text-slate-600">
                Aucune annonce ni aucun dossier sur cette période.
              </p>
            ) : (
              <div className="overflow-x-auto">
                <table className="w-full text-sm">
                  <thead>
                    <tr className={tableHead}>
                      <th className={HEAD}>Plateforme</th>
                      <th className={HEAD}>Récupération</th>
                      <th className={`${NUM} font-semibold`}>
                        Annonces publiées
                      </th>
                      <th className={`${NUM} font-semibold`}>
                        {org ? "Retenues pour l'entreprise" : "Retenues"}
                      </th>
                      <th className={`${NUM} font-semibold`}>Dossiers</th>
                    </tr>
                  </thead>
                  <tbody>
                    {d.rows.map((r) => (
                      <tr key={r.platform} className={tableRow}>
                        <td className={`${CELL} font-medium`}>{r.platform}</td>
                        <td className={CELL}>
                          <Badge tone={RETRIEVAL[r.retrieval].tone}>
                            {RETRIEVAL[r.retrieval].label}
                          </Badge>
                        </td>
                        <td className={NUM}>{r.notices}</td>
                        <td className={NUM}>{r.matched}</td>
                        <td className={NUM}>{r.dossiers}</td>
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
