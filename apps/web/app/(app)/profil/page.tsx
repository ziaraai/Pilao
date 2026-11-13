"use client";

import { usePathname, useRouter, useSearchParams } from "next/navigation";
import { Suspense, useRef, useState } from "react";

import { CompanyIdentity } from "@/components/profile/company-identity";
import { DceRetrievalSettings } from "@/components/profile/dce-retrieval";
import { DataRights } from "@/components/profile/data-rights";
import { PlanCredits } from "@/components/profile/plan-credits";
import { ProfilePrefill } from "@/components/profile/prefill";
import { Members } from "@/components/profile/members";
import { References } from "@/components/profile/references";
import { SimpleList } from "@/components/profile/simple-list";
import { WatchSettings } from "@/components/profile/watch-settings";
import { Alert, Card, Loading, PageTitle } from "@/components/ui";
import { useMe } from "@/lib/auth";
import { formatDate } from "@/lib/format";
import { useApi } from "@/lib/hooks";
import { hasModule } from "@/lib/modules";
import type { Completeness, Profile, Trade } from "@/lib/types";

// One tab per part of the profile; `keys` are the completeness items it holds.
const TABS = [
  { id: "identite", label: "Identité", keys: ["identity"] },
  {
    id: "veille",
    label: "Métiers et veille",
    keys: ["trades", "watch", "departments"],
  },
  { id: "chiffre-affaires", label: "Chiffre d'affaires", keys: ["revenue"] },
  { id: "moyens", label: "Moyens", keys: ["human_resources", "equipment"] },
  { id: "certifications", label: "Certifications", keys: ["certifications"] },
  { id: "references", label: "Références", keys: ["references"] },
  { id: "utilisateurs", label: "Utilisateurs", keys: [] },
  { id: "formule", label: "Formule et crédits", keys: [] },
  { id: "donnees", label: "Vos données", keys: [] },
] as const;
type TabId = (typeof TABS)[number]["id"];

function tabOf(key: string): TabId {
  return (
    TABS.find((t) => (t.keys as readonly string[]).includes(key))?.id ??
    "identite"
  );
}

export default function ProfilePage() {
  return (
    <Suspense fallback={<Loading />}>
      <ProfileTabs />
    </Suspense>
  );
}

function ProfileTabs() {
  const { me } = useMe();
  const watch = hasModule(me.modules, "veille"); // without it, only the trades of that tab
  const answers = hasModule(me.modules, "reponse"); // the prefill reads its document base
  const router = useRouter();
  const pathname = usePathname();
  const params = useSearchParams();
  const profile = useApi<Profile>("/profile");
  const trades = useApi<Trade[]>("/profile/trades");
  const completeness = useApi<Completeness>("/profile/completeness");
  const tabs = useRef<(HTMLButtonElement | null)[]>([]);
  const [version, setVersion] = useState(0); // lines added from the documents: reload the lists

  const asked = params.get("onglet");
  const current: TabId = TABS.some((t) => t.id === asked)
    ? (asked as TabId)
    : "identite";
  // The tab is in the address: a reload or a link (« Annuler ou exporter ») opens it.
  const open = (id: TabId) =>
    router.replace(`${pathname}?onglet=${id}`, { scroll: false });

  if (profile.error || trades.error)
    return <Alert tone="danger">{profile.error ?? trades.error}</Alert>;
  if (!profile.data || !trades.data) return <Loading />;
  const c = completeness.data ?? profile.data.completeness;
  const keys = c.missing_keys ?? [];
  const missingIn = (id: TabId) => keys.filter((k) => tabOf(k) === id).length;

  function onKeyDown(e: React.KeyboardEvent, index: number) {
    const step = e.key === "ArrowRight" ? 1 : e.key === "ArrowLeft" ? -1 : 0;
    if (!step) return;
    e.preventDefault();
    const next = (index + step + TABS.length) % TABS.length;
    open(TABS[next].id);
    tabs.current[next]?.focus();
  }

  return (
    <div className="space-y-6">
      <PageTitle
        title="Profil de l'entreprise"
        subtitle={`${me.org.name} — SIRET ${me.org.siret}`}
        icon="profile"
        color="brand"
      />
      <Card title={`Profil complet à ${c.pct} %`} color="brand">
        <div
          className="h-3 w-full overflow-hidden rounded-full bg-slate-200"
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
          <div className="mt-3">
            <p className="text-sm text-slate-700">À compléter :</p>
            <ul className="mt-2 flex flex-wrap gap-2">
              {c.missing.map((label, i) => (
                <li key={label}>
                  <button
                    type="button"
                    onClick={() => open(tabOf(keys[i] ?? ""))}
                    className="rounded-full bg-amber-50 px-3 py-1 text-xs font-medium text-amber-900 ring-1 ring-inset ring-amber-200 hover:bg-amber-100"
                  >
                    {label}
                  </button>
                </li>
              ))}
            </ul>
          </div>
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

      {answers && (
        <ProfilePrefill
          onAdded={() => {
            completeness.reload();
            setVersion((v) => v + 1);
          }}
        />
      )}

      <div
        role="tablist"
        aria-label="Parties du profil"
        className="-mx-4 flex gap-1 overflow-x-auto overflow-y-hidden border-b-2 border-slate-300 px-4 lg:mx-0 lg:px-0"
      >
        {TABS.map((t, i) => {
          const selected = t.id === current;
          const missing = missingIn(t.id);
          return (
            <button
              key={t.id}
              ref={(el) => {
                tabs.current[i] = el;
              }}
              type="button"
              role="tab"
              id={`tab-${t.id}`}
              aria-selected={selected}
              aria-controls={`panel-${t.id}`}
              tabIndex={selected ? 0 : -1}
              onClick={() => open(t.id)}
              onKeyDown={(e) => onKeyDown(e, i)}
              className={`-mb-0.5 inline-flex shrink-0 items-center gap-2 whitespace-nowrap rounded-t-md border-b-2 px-3 py-2.5 text-sm ${selected ? "border-brand-green bg-[#dcfbf1] font-bold text-brand-navy" : "border-transparent font-medium text-slate-700 hover:bg-white hover:text-slate-900"}`}
            >
              {t.id === "veille" && !watch ? "Métiers" : t.label}
              {missing > 0 && (
                <span
                  className="rounded-full bg-amber-100 px-1.5 text-xs font-semibold text-amber-900"
                  aria-label={`${missing} à compléter`}
                >
                  {missing}
                </span>
              )}
            </button>
          );
        })}
      </div>

      <div
        key={`${current}-${version}`}
        role="tabpanel"
        id={`panel-${current}`}
        aria-labelledby={`tab-${current}`}
        className="space-y-6"
      >
        {current === "identite" && <CompanyIdentity />}
        {current === "identite" && answers && <DceRetrievalSettings />}
        {(current === "veille" || current === "chiffre-affaires") && (
          <WatchSettings
            key={current} // a fresh form from the saved profile on each tab
            part={current === "veille" ? "watch" : "revenue"}
            watch={watch}
            profile={profile.data}
            trades={trades.data}
            onSaved={(p) => {
              profile.setData(p);
              completeness.reload();
            }}
          />
        )}
        {current === "moyens" && (
          <>
            <SimpleList
              title="Moyens humains"
              path="/profile/human-resources"
              onChange={completeness.reload}
              excel={{ what: "ligne(s) de moyens humains" }}
              emptyText="Aucun moyen humain : ajoutez vos équipes (ex. 12 agents de service)."
              columns={[
                {
                  key: "qualification",
                  label: "Qualification",
                  required: true,
                },
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
              excel={{ what: "ligne(s) de matériel" }}
              emptyText="Aucun matériel : ajoutez vos machines (ex. autolaveuse)."
              columns={[
                { key: "name", label: "Matériel", required: true },
                {
                  key: "category",
                  label: "Type de matériel",
                  placeholder: "ex. autolaveuse, monobrosse",
                  hint: "sert à regrouper votre matériel par type dans la liste des moyens matériels du dossier.",
                },
                {
                  key: "quantity",
                  label: "Quantité",
                  type: "number",
                  render: (v) => `× ${String(v)}`,
                },
              ]}
            />
          </>
        )}
        {current === "certifications" && (
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
        )}
        {current === "references" && (
          <References onChange={completeness.reload} />
        )}
        {current === "utilisateurs" && <Members />}
        {current === "formule" && <PlanCredits />}
        {current === "donnees" && <DataRights />}
      </div>
    </div>
  );
}
