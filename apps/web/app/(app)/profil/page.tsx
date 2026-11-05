"use client";

import { CompanyIdentity } from "@/components/profile/company-identity";
import { DataRights } from "@/components/profile/data-rights";
import { References } from "@/components/profile/references";
import { SimpleList } from "@/components/profile/simple-list";
import { WatchSettings } from "@/components/profile/watch-settings";
import { Alert, Card, Loading, PageTitle } from "@/components/ui";
import { useMe } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import type { Completeness, Profile, Trade } from "@/lib/types";

export default function ProfilePage() {
  const { me } = useMe();
  const profile = useApi<Profile>("/profile");
  const trades = useApi<Trade[]>("/profile/trades");
  const completeness = useApi<Completeness>("/profile/completeness");

  if (profile.error || trades.error)
    return <Alert tone="danger">{profile.error ?? trades.error}</Alert>;
  if (!profile.data || !trades.data) return <Loading />;
  const c = completeness.data ?? profile.data.completeness;

  return (
    <div className="space-y-6">
      <PageTitle
        title="Profil de l'entreprise"
        subtitle={`${me.org.name} — SIRET ${me.org.siret}`}
      />
      <Card title={`Profil complet à ${c.pct} %`}>
        <div
          className="h-2 w-full overflow-hidden rounded-full bg-slate-100"
          role="progressbar"
          aria-valuenow={c.pct}
          aria-valuemin={0}
          aria-valuemax={100}
          aria-label="Complétude du profil"
        >
          <div
            className="h-full bg-brand-green transition-all"
            style={{ width: `${c.pct}%` }}
          />
        </div>
        {c.missing.length > 0 ? (
          <ul className="mt-3 list-inside list-disc text-sm text-slate-700">
            {c.missing.map((m) => (
              <li key={m}>{m}</li>
            ))}
          </ul>
        ) : (
          <p className="mt-3 text-sm text-slate-700">
            Votre profil est complet : vos mémoires pourront s&apos;appuyer sur
            toutes vos informations.
          </p>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Seules les informations saisies ici sont utilisées dans vos mémoires :
          rien n&apos;est inventé.
        </p>
      </Card>
      <CompanyIdentity />
      <WatchSettings
        profile={profile.data}
        trades={trades.data}
        onSaved={(p) => {
          profile.setData(p);
          completeness.reload();
        }}
      />
      <SimpleList
        title="Moyens humains"
        path="/profile/human-resources"
        onChange={completeness.reload}
        emptyText="Aucun moyen humain : ajoutez vos équipes (ex. 12 agents de service)."
        columns={[
          { key: "qualification", label: "Qualification", required: true },
          {
            key: "count",
            label: "Nombre",
            type: "number",
            required: true,
            render: (v) => `× ${String(v)}`,
          },
          { key: "description", label: "Précisions" },
        ]}
      />
      <SimpleList
        title="Moyens matériels"
        path="/profile/equipment"
        onChange={completeness.reload}
        emptyText="Aucun matériel : ajoutez vos machines (ex. autolaveuse)."
        columns={[
          { key: "name", label: "Matériel", required: true },
          { key: "category", label: "Catégorie" },
          {
            key: "quantity",
            label: "Quantité",
            type: "number",
            render: (v) => `× ${String(v)}`,
          },
        ]}
      />
      <SimpleList
        title="Certifications"
        path="/profile/certifications"
        onChange={completeness.reload}
        emptyText="Aucune certification (ISO 9001, Qualipropre…)."
        columns={[
          { key: "name", label: "Certification", required: true },
          { key: "number", label: "Numéro" },
          {
            key: "valid_until",
            label: "Valable jusqu'au",
            type: "date",
            render: (v) => `jusqu'au ${formatDate(String(v))}`,
          },
        ]}
      />
      <References onChange={completeness.reload} />
      <DataRights />
    </div>
  );
}
