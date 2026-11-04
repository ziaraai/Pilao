"use client";

import { useState } from "react";

import {
  Alert,
  Badge,
  Button,
  Card,
  Empty,
  Input,
  Loading,
  Select,
} from "@/components/ui";
import { api } from "@/lib/api";
import { formatCents } from "@/lib/format";
import { useAction, useApi } from "@/lib/hooks";
import type { Analysis, Memoir } from "@/lib/types";

const SOURCE_LABEL: Record<Memoir["outline_source"], string> = {
  rc_imposed:
    "Plan imposé par le règlement de la consultation (repris à l'identique)",
  org_template:
    "Plan de votre mémoire modèle, ordonné selon les critères de notation",
  sector_default:
    "Plan type du nettoyage (aucun plan imposé ni mémoire modèle)",
};

type Draft = {
  id?: string;
  title: string;
  requirement_refs: string[];
  word_budget: number;
};

export function MemoirSection({ bidId }: { bidId: string }) {
  const memoir = useApi<Memoir>(`/bids/${bidId}/memoir`);
  const analysis = useApi<Analysis>(`/bids/${bidId}/analysis`);
  const create = useAction();

  async function prepare() {
    const m = await create.run(() =>
      api<Memoir>(`/bids/${bidId}/memoir`, { method: "POST" }),
    );
    if (m) memoir.setData(m);
  }

  const ready = analysis.data?.status === "ready";
  if (!memoir.data) {
    return (
      <Card title="Mémoire technique">
        {memoir.loading ? (
          <Loading />
        ) : (
          <div className="space-y-3">
            <p className="text-sm text-slate-600">
              Le plan du mémoire est préparé à partir de l&apos;analyse : plan
              imposé par le RC s&apos;il existe, sinon votre mémoire modèle,
              sinon le plan type du secteur. Vous pourrez le modifier avant la
              rédaction.
            </p>
            <Button onClick={prepare} busy={create.busy} disabled={!ready}>
              Préparer le plan du mémoire
            </Button>
            {!ready && (
              <p className="text-xs text-slate-500">
                Disponible quand l&apos;analyse du DCE est prête.
              </p>
            )}
            {create.error && <Alert tone="danger">{create.error}</Alert>}
          </div>
        )}
      </Card>
    );
  }
  return (
    <OutlineEditor
      key={`${memoir.data.id}:${memoir.data.sections.map((s) => s.id).join(",")}`}
      memoir={memoir.data}
      allRefs={
        analysis.data?.requirements.map((r) => ({
          ref: r.ref,
          text: r.text,
        })) ?? []
      }
      onChange={memoir.setData}
      onNewVersion={prepare}
      busyNewVersion={create.busy}
    />
  );
}

function OutlineEditor({
  memoir,
  allRefs,
  onChange,
  onNewVersion,
  busyNewVersion,
}: {
  memoir: Memoir;
  allRefs: { ref: string; text: string }[];
  onChange: (m: Memoir) => void;
  onNewVersion: () => void;
  busyNewVersion: boolean;
}) {
  const [sections, setSections] = useState<Draft[]>(() =>
    memoir.sections.map((s) => ({
      id: s.id,
      title: s.title,
      requirement_refs: s.requirement_refs,
      word_budget: s.word_budget,
    })),
  );
  const [dirty, setDirty] = useState(false);
  const save = useAction();
  const refs = useAction();
  const editable = memoir.status === "draft";
  const assigned = new Set(sections.flatMap((s) => s.requirement_refs));
  const unassigned = allRefs.filter((r) => !assigned.has(r.ref));
  const textOf = Object.fromEntries(allRefs.map((r) => [r.ref, r.text]));

  function change(i: number, patch: Partial<Draft>) {
    setDirty(true);
    setSections((all) => all.map((s, j) => (j === i ? { ...s, ...patch } : s)));
  }
  function move(i: number, delta: number) {
    setDirty(true);
    setSections((all) => {
      const next = [...all];
      const [item] = next.splice(i, 1);
      next.splice(i + delta, 0, item);
      return next;
    });
  }

  return (
    <div className="space-y-6">
      <Card
        title={`Plan du mémoire — version ${memoir.version}`}
        actions={
          <div className="flex gap-2">
            {editable && (
              <Button
                busy={save.busy}
                disabled={!dirty}
                onClick={async () => {
                  const m = await save.run(() =>
                    api<Memoir>(`/memoirs/${memoir.id}/outline`, {
                      method: "PUT",
                      json: { sections },
                    }),
                  );
                  if (m) {
                    setDirty(false);
                    onChange(m);
                  }
                }}
              >
                Enregistrer le plan
              </Button>
            )}
            <Button
              variant="secondary"
              busy={busyNewVersion}
              onClick={onNewVersion}
            >
              Nouvelle version
            </Button>
          </div>
        }
      >
        <p className="mb-1 text-sm text-slate-700">
          {SOURCE_LABEL[memoir.outline_source]}.
        </p>
        <p className="mb-4 text-xs text-slate-500">
          Environ {sections.reduce((n, s) => n + s.word_budget, 0)} mots (
          {Math.ceil(sections.reduce((n, s) => n + s.word_budget, 0) / 500)}{" "}
          pages)
          {memoir.max_pages ? ` pour ${memoir.max_pages} pages maximum` : ""}.
        </p>
        {memoir.outline_source === "rc_imposed" && editable && (
          <div className="mb-4">
            <Alert tone="warning">
              Plan imposé : en changer les titres ou l&apos;ordre peut vous
              pénaliser.
            </Alert>
          </div>
        )}
        {unassigned.length > 0 && (
          <div className="mb-4">
            <Alert tone="warning">
              Exigences rattachées à aucun chapitre :{" "}
              {unassigned.map((r) => r.ref).join(", ")}.
            </Alert>
          </div>
        )}
        <ol className="space-y-3">
          {sections.map((s, i) => (
            <li
              key={s.id ?? `new-${i}`}
              className="rounded-md p-3 ring-1 ring-slate-200"
            >
              <div className="flex flex-wrap items-center gap-2">
                <span className="w-6 text-sm font-semibold text-slate-500">
                  {i + 1}.
                </span>
                <label htmlFor={`title-${i}`} className="sr-only">
                  Titre du chapitre {i + 1}
                </label>
                <Input
                  id={`title-${i}`}
                  value={s.title}
                  disabled={!editable}
                  onChange={(e) => change(i, { title: e.target.value })}
                  className="min-w-64 flex-1"
                />
                <label htmlFor={`words-${i}`} className="sr-only">
                  Nombre de mots du chapitre {i + 1}
                </label>
                <Input
                  id={`words-${i}`}
                  type="number"
                  min={50}
                  step={50}
                  value={s.word_budget}
                  disabled={!editable}
                  onChange={(e) =>
                    change(i, { word_budget: Number(e.target.value) || 50 })
                  }
                  className="w-24"
                />
                <span className="text-xs text-slate-500">mots</span>
                {editable && (
                  <span className="flex gap-1">
                    <Button
                      variant="ghost"
                      aria-label={`Monter le chapitre ${i + 1}`}
                      disabled={i === 0}
                      onClick={() => move(i, -1)}
                    >
                      ↑
                    </Button>
                    <Button
                      variant="ghost"
                      aria-label={`Descendre le chapitre ${i + 1}`}
                      disabled={i === sections.length - 1}
                      onClick={() => move(i, 1)}
                    >
                      ↓
                    </Button>
                    <Button
                      variant="ghost"
                      aria-label={`Supprimer le chapitre ${i + 1}`}
                      disabled={sections.length === 1}
                      onClick={() => {
                        setDirty(true);
                        setSections((all) => all.filter((_, j) => j !== i));
                      }}
                    >
                      ✕
                    </Button>
                  </span>
                )}
              </div>
              {memoir.sections.find((m) => m.id === s.id)?.criterion_ref && (
                <p className="ml-8 mt-1 text-xs text-slate-500">
                  Critère :{" "}
                  {memoir.sections.find((m) => m.id === s.id)?.criterion_ref}
                </p>
              )}
              <div className="ml-8 mt-2 flex flex-wrap items-center gap-1.5">
                {s.requirement_refs.map((ref) => (
                  <span
                    key={ref}
                    title={textOf[ref]}
                    className="inline-flex items-center gap-1 rounded-full bg-slate-100 px-2 py-0.5 font-mono text-xs text-slate-700"
                  >
                    {ref}
                    {editable && (
                      <button
                        type="button"
                        aria-label={`Retirer ${ref}`}
                        onClick={() =>
                          change(i, {
                            requirement_refs: s.requirement_refs.filter(
                              (r) => r !== ref,
                            ),
                          })
                        }
                      >
                        ×
                      </button>
                    )}
                  </span>
                ))}
                {editable && allRefs.length > 0 && (
                  <>
                    <label htmlFor={`add-${i}`} className="sr-only">
                      Ajouter une exigence au chapitre {i + 1}
                    </label>
                    <Select
                      id={`add-${i}`}
                      value=""
                      className="w-auto py-1 text-xs"
                      onChange={(e) =>
                        e.target.value &&
                        change(i, {
                          requirement_refs: [
                            ...s.requirement_refs,
                            e.target.value,
                          ],
                        })
                      }
                    >
                      <option value="">+ exigence</option>
                      {allRefs
                        .filter((r) => !s.requirement_refs.includes(r.ref))
                        .map((r) => (
                          <option key={r.ref} value={r.ref}>
                            {r.ref} — {r.text.slice(0, 60)}
                          </option>
                        ))}
                    </Select>
                  </>
                )}
              </div>
            </li>
          ))}
        </ol>
        {editable && (
          <div className="mt-3">
            <Button
              variant="secondary"
              onClick={() => {
                setDirty(true);
                setSections((all) => [
                  ...all,
                  {
                    title: "Nouveau chapitre",
                    requirement_refs: [],
                    word_budget: 300,
                  },
                ]);
              }}
            >
              Ajouter un chapitre
            </Button>
          </div>
        )}
        {save.error && (
          <div className="mt-3">
            <Alert tone="danger">{save.error}</Alert>
          </div>
        )}
      </Card>
      <Card title="Références citées dans le mémoire">
        {memoir.references.length === 0 ? (
          <Empty>
            Aucune référence dans votre profil : ajoutez vos chantiers dans
            Profil pour les citer.
          </Empty>
        ) : (
          <ul className="divide-y divide-slate-100">
            {memoir.references.map((r) => (
              <li
                key={r.id}
                className="flex flex-wrap items-start gap-3 py-2 text-sm"
              >
                <input
                  id={`ref-${r.id}`}
                  type="checkbox"
                  className="mt-1"
                  checked={r.selected}
                  disabled={!editable || refs.busy}
                  onChange={async (e) => {
                    const ids = memoir.references
                      .filter((x) =>
                        x.id === r.id ? e.target.checked : x.selected,
                      )
                      .map((x) => x.id);
                    const m = await refs.run(() =>
                      api<Memoir>(`/memoirs/${memoir.id}/references`, {
                        method: "PUT",
                        json: { reference_ids: ids },
                      }),
                    );
                    if (m) onChange(m);
                  }}
                />
                <label htmlFor={`ref-${r.id}`} className="flex-1">
                  <span className="font-medium">{r.title}</span> —{" "}
                  {r.client_name}
                  {r.year && `, ${r.year}`}
                  {r.amount_cents != null && `, ${formatCents(r.amount_cents)}`}
                  <span className="mt-1 flex flex-wrap gap-1">
                    {r.reasons.map((why) => (
                      <Badge key={why} tone="info">
                        {why}
                      </Badge>
                    ))}
                  </span>
                </label>
              </li>
            ))}
          </ul>
        )}
        {refs.error && (
          <div className="mt-3">
            <Alert tone="danger">{refs.error}</Alert>
          </div>
        )}
        <p className="mt-3 text-xs text-slate-500">
          Seules vos propres références sont proposées : aucune n&apos;est
          inventée.
        </p>
      </Card>
      <Card title="Rédaction">
        <p className="text-sm text-slate-600">
          La rédaction chapitre par chapitre s&apos;appuiera sur ce plan, vos
          références et votre base documentaire.
        </p>
      </Card>
    </div>
  );
}
