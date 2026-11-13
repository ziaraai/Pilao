"use client";

import { Fragment, useState } from "react";

import { ApiKeyCard } from "@/components/admin/api-key-card";
import { DceRobotCard } from "@/components/admin/dce-robot-card";
import { ModelPicker } from "@/components/admin/model-picker";
import {
  AdminTitle,
  CELL,
  HEAD,
  Loaded,
  NUM,
  Pill,
} from "@/components/admin/ui";
import {
  Alert,
  Button,
  Card,
  Input,
  tableHead,
  tableRow,
} from "@/components/ui";
import { useAdminAction, useAdminApi } from "@/lib/admin-auth";
import { api } from "@/lib/api";
import { creditInput } from "@/lib/credits";
import { formatDateTimeShort, formatEuros } from "@/lib/format";
import { eur, originLabel } from "@/lib/settings";
import type {
  AdminGeneralSetting,
  AdminImportSetting,
  AdminModelSetting,
  AdminSettings,
} from "@/lib/types";

const PASS_STATUS: Record<string, string> = {
  done: "réussi",
  error: "en erreur",
  running: "en cours",
};

function Origin({ source }: { source: "admin" | "server" }) {
  return (
    <Pill tone={source === "admin" ? "ok" : "neutral"}>
      {originLabel(source)}
    </Pill>
  );
}

type Run = (fn: () => Promise<unknown>) => Promise<boolean>;

/** Lot 5 (US-6.15 to US-6.18): what used to need the server file or a GitHub secret. */
export default function AdminSettingsPage() {
  const state = useAdminApi<AdminSettings>("/admin/settings");
  const act = useAdminAction();
  const [notice, setNotice] = useState<string | null>(null);

  const run: Run = async (fn) => {
    setNotice(null);
    const done = await act.run(async () => (await fn(), true));
    if (done) state.reload();
    return Boolean(done);
  };

  return (
    <div className="space-y-6">
      <AdminTitle
        title="Réglages"
        readOnly={false}
        subtitle="Ce que vous réglez ici remplace la valeur du serveur, pour tout le site, en moins d'une minute. Chaque changement va au journal."
      />
      {act.error && <Alert tone="danger">{act.error}</Alert>}
      {notice && <Alert tone="ok">{notice}</Alert>}
      <Loaded state={state}>
        {(s) => (
          <>
            <Models
              models={s.models}
              embedding={s.embedding_model}
              run={run}
              reload={state.reload}
            />
            <ApiKeyCard apiKey={s.api_key} onSaved={state.reload} />
            <Imports imports={s.imports} run={run} onStarted={setNotice} />
            <DceRobotCard robot={s.dce_robot} run={run} />
            <General settings={s.general} run={run} />
          </>
        )}
      </Loaded>
    </div>
  );
}

function Models({
  models,
  embedding,
  run,
  reload,
}: {
  models: AdminModelSetting[];
  embedding: string;
  run: Run;
  reload: () => void;
}) {
  const [picking, setPicking] = useState<string | null>(null);
  return (
    <Card title="Modèles d'IA" color="brand" flush>
      <div className="overflow-x-auto">
        <table className="w-full text-sm">
          <thead>
            <tr className={tableHead}>
              <th className={HEAD}>Tâche</th>
              <th className={HEAD}>Modèle</th>
              <th className={NUM}>Prix par million (entrée / sortie)</th>
              <th className={HEAD}>Origine</th>
              <th className={NUM}>Coût réel (30 j)</th>
              <th className={HEAD} />
            </tr>
          </thead>
          <tbody>
            {models.map((m) => (
              <Fragment key={m.task}>
                <tr className={tableRow}>
                  <td className={`${CELL} font-medium`}>{m.label}</td>
                  <td className={CELL}>
                    {m.model ? (
                      <>
                        <span className="block">{m.model_name ?? m.model}</span>
                        <span className="block break-all text-xs text-slate-500">
                          {m.model}
                        </span>
                      </>
                    ) : (
                      <span className="text-slate-500">Aucun modèle</span>
                    )}
                    {m.in_catalogue === false && (
                      <span className="mt-1 block text-xs font-semibold text-amber-800">
                        Ce modèle n&apos;est plus au catalogue
                        d&apos;OpenRouter.
                      </span>
                    )}
                  </td>
                  <td className={NUM}>
                    {eur(m.price_in_eur)} / {eur(m.price_out_eur)}
                  </td>
                  <td className={CELL}>
                    <Origin source={m.source} />
                  </td>
                  <td className={NUM}>
                    {formatEuros(m.cost_30d_eur)}
                    <span className="block text-xs text-slate-500">
                      {m.calls_30d} appel{m.calls_30d > 1 ? "s" : ""}
                    </span>
                  </td>
                  <td className={CELL}>
                    <span className="flex flex-wrap justify-end gap-2">
                      <Button
                        variant="secondary"
                        className="px-2 py-1 text-xs"
                        aria-expanded={picking === m.task}
                        aria-label={`Changer le modèle de « ${m.label} »`}
                        onClick={() =>
                          setPicking(picking === m.task ? null : m.task)
                        }
                      >
                        Changer
                      </Button>
                      <Button
                        variant="ghost"
                        className="px-2 py-1 text-xs"
                        disabled={m.source === "server" || !m.server_model}
                        aria-label={`Revenir à la valeur du serveur pour « ${m.label} »`}
                        onClick={() =>
                          run(() =>
                            api(`/admin/settings/models/${m.task}`, {
                              method: "DELETE",
                            }),
                          )
                        }
                      >
                        Revenir à la valeur du serveur
                      </Button>
                    </span>
                  </td>
                </tr>
                {picking === m.task && (
                  <tr>
                    <td colSpan={6} className="p-0">
                      <ModelPicker
                        task={m.task}
                        label={m.label}
                        onCancel={() => setPicking(null)}
                        onSaved={() => {
                          setPicking(null);
                          reload();
                        }}
                      />
                    </td>
                  </tr>
                )}
              </Fragment>
            ))}
          </tbody>
        </table>
      </div>
      <p className="px-5 py-3 text-xs text-slate-500">
        Modèle d&apos;indexation de la base documentaire :{" "}
        {embedding || "aucun"} (réglé sur le serveur : en changer oblige à
        réindexer tous les documents).
      </p>
    </Card>
  );
}

function Imports({
  imports,
  run,
  onStarted,
}: {
  imports: AdminImportSetting[];
  run: Run;
  onStarted: (message: string) => void;
}) {
  return (
    <Card title="Imports d'annonces" color="sky">
      <ul className="divide-y divide-slate-200">
        {imports.map((i) => (
          <li
            key={i.source}
            className="flex flex-wrap items-center justify-between gap-3 py-3 first:pt-0 last:pb-0"
          >
            <div className="min-w-0 space-y-1">
              <p className="flex flex-wrap items-center gap-2 font-semibold text-brand-navy">
                {i.label} <Origin source={i.origin} />
              </p>
              <p className="text-xs text-slate-600">
                {i.last
                  ? `Dernier passage : ${formatDateTimeShort(i.last.started_at)}, ${PASS_STATUS[i.last.status] ?? i.last.status} — ${i.last.created} nouvelle${i.last.created > 1 ? "s" : ""}, ${i.last.updated} mise${i.last.updated > 1 ? "s" : ""} à jour`
                  : "Aucun passage pour l'instant."}
              </p>
              {i.last?.error && (
                <p className="text-xs text-red-700">{i.last.error}</p>
              )}
            </div>
            <div className="flex flex-wrap items-center gap-3">
              <label className="flex items-center gap-2 text-sm">
                <input
                  type="checkbox"
                  className="h-4 w-4"
                  checked={i.enabled}
                  aria-label={`${i.label} actif`}
                  onChange={(e) =>
                    run(() =>
                      api(`/admin/settings/imports/${i.source}`, {
                        method: "PUT",
                        json: { enabled: e.target.checked },
                      }),
                    )
                  }
                />
                Actif
              </label>
              {i.enabled && (
                <Button
                  variant="secondary"
                  className="px-2 py-1 text-xs"
                  onClick={async () => {
                    const done = await run(() =>
                      api(`/admin/settings/imports/${i.source}/run`, {
                        method: "POST",
                      }),
                    );
                    if (done)
                      onStarted(
                        "Passage lancé : il apparaîtra dans Technique.",
                      );
                  }}
                >
                  Importer maintenant
                </Button>
              )}
              {i.origin === "admin" && (
                <Button
                  variant="ghost"
                  className="px-2 py-1 text-xs"
                  onClick={() =>
                    run(() =>
                      api(`/admin/settings/imports/${i.source}`, {
                        method: "DELETE",
                      }),
                    )
                  }
                >
                  Revenir à la valeur du serveur
                </Button>
              )}
            </div>
          </li>
        ))}
      </ul>
      <p className="mt-3 text-xs text-slate-500">
        Toutes les 2 heures, le planificateur n&apos;importe que les sources
        actives.
      </p>
    </Card>
  );
}

function shownValue(v: number | string | null): string {
  return v === null || v === "" ? "aucune" : String(v);
}

function General({
  settings,
  run,
}: {
  settings: AdminGeneralSetting[];
  run: Run;
}) {
  return (
    <Card title="Réglages généraux" color="slate">
      <div className="space-y-5">
        {settings.map((g) => (
          <GeneralRow key={g.name} setting={g} run={run} />
        ))}
      </div>
    </Card>
  );
}

function GeneralRow({
  setting: g,
  run,
}: {
  setting: AdminGeneralSetting;
  run: Run;
}) {
  const [typed, setTyped] = useState(g.value === null ? "" : String(g.value));
  const budget = g.kind === "int" ? creditInput(typed, 10000) : null;
  const valid = g.kind === "int" ? budget !== null && budget >= 1 : true;
  const id = `general-${g.name}`;
  return (
    <div className="space-y-1">
      <label
        htmlFor={id}
        className="block text-sm font-semibold text-brand-navy"
      >
        {g.label} {g.kind === "int" && "(en euros)"}
      </label>
      <div className="flex flex-wrap items-center gap-2">
        <Input
          id={id}
          type={g.kind === "int" ? "number" : "email"}
          min={g.kind === "int" ? 1 : undefined}
          max={g.kind === "int" ? 10000 : undefined}
          className={g.kind === "int" ? "w-28" : "min-w-0 flex-1"}
          value={typed}
          onChange={(e) => setTyped(e.target.value)}
        />
        <Button
          className="px-2 py-1 text-xs"
          aria-label={`Enregistrer « ${g.label} »`}
          disabled={!valid || typed === String(g.value ?? "")}
          onClick={() =>
            run(() =>
              api(`/admin/settings/general/${g.name}`, {
                method: "PUT",
                json: { value: g.kind === "int" ? budget : typed.trim() },
              }),
            )
          }
        >
          Enregistrer
        </Button>
        <Button
          variant="ghost"
          className="px-2 py-1 text-xs"
          disabled={g.source === "server"}
          onClick={async () => {
            if (
              await run(() =>
                api(`/admin/settings/general/${g.name}`, { method: "DELETE" }),
              )
            )
              setTyped(g.server_value === null ? "" : String(g.server_value));
          }}
        >
          Revenir à la valeur du serveur
        </Button>
      </div>
      <p className="text-xs text-slate-500">
        <Origin source={g.source} /> Valeur du serveur :{" "}
        {shownValue(g.server_value)}
      </p>
    </div>
  );
}
